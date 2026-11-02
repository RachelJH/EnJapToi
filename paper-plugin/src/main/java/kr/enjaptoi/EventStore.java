package kr.enjaptoi;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.*;
import java.sql.*;
import java.util.*;

/** Durable receipts and execution intent; game effects are NOT DB transactions. */
final class EventStore implements AutoCloseable {
  record Event(String id, String effect, int cheese, String donor) {
    @Override public String toString(){return "Event[redacted]";} // Do not expose the display name in incidental diagnostics.
  }
  enum Receipt { QUEUED, DUPLICATE, CONFLICT }
  @FunctionalInterface interface Committer { void commit(Connection c) throws SQLException; }
  @FunctionalInterface private interface Work<T> { T run() throws SQLException; }
  private Connection db;
  private FileChannel lockChannel;
  private FileLock fileLock;
  private final Committer committer;
  private boolean healthy = true;
  private static final Set<String> EFFECTS = Set.of("buff","move","bread","pickaxe","mob","debuff","clear","chancekill","surface","kill");

  EventStore(Path path) throws SQLException, IOException { this(path, Connection::commit); }
  EventStore(Path path, Committer committer) throws SQLException, IOException {
    this.committer = committer;
    Files.createDirectories(path.toAbsolutePath().getParent());
    try {
      lockChannel = FileChannel.open(path.resolveSibling(path.getFileName()+".lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE);
      fileLock = lockChannel.tryLock();
      if (fileLock == null) throw new IOException("Event store already in use");
      Class.forName("org.sqlite.JDBC");
      db = DriverManager.getConnection("jdbc:sqlite:"+path.toAbsolutePath());
      try (Statement s = db.createStatement()) {
        s.execute("PRAGMA busy_timeout=2000");
        s.execute("PRAGMA journal_mode=DELETE");
        s.execute("PRAGMA synchronous=FULL");
        s.execute("PRAGMA secure_delete=ON");
        s.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, effect TEXT, state TEXT NOT NULL CHECK(state IN ('PENDING','RUNNING','DONE','UNCERTAIN')))");
        boolean hasCheese=false,hasDonor=false;
        try(ResultSet columns=s.executeQuery("PRAGMA table_info(events)")){while(columns.next()){if(columns.getString("name").equals("cheese"))hasCheese=true;if(columns.getString("name").equals("donor"))hasDonor=true;}}
        if(!hasCheese)s.execute("ALTER TABLE events ADD COLUMN cheese INTEGER NOT NULL DEFAULT 0");
        if(!hasDonor)s.execute("ALTER TABLE events ADD COLUMN donor TEXT");
        s.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)");
      }
      transaction(() -> {
        try (Statement s = db.createStatement()) {
          int changed = s.executeUpdate("UPDATE events SET state='UNCERTAIN',donor=NULL WHERE state='RUNNING'");
          if (changed > 0) writePaused(true);
        }
        return null;
      });
    } catch (Exception e) {
      close();
      if (e instanceof SQLException sql) throw sql;
      throw new IOException("Event store initialization failed", e);
    }
  }

  private void check() throws SQLException {
    if (!healthy || db == null) throw new SQLException("Event store unavailable; restart required");
  }
  private <T> T transaction(Work<T> work) throws SQLException {
    check();
    try {
      db.setAutoCommit(false);
      T result = work.run();
      committer.commit(db); // ACK / in-memory effects may only follow this boundary.
      db.setAutoCommit(true);
      return result;
    } catch (SQLException | RuntimeException e) {
      healthy = false; // Commit outcome may be ambiguous. Never use this connection to ACK again.
      try { db.rollback(); } catch (SQLException ignored) {}
      throw e;
    }
  }

  synchronized Receipt enqueue(String id, String effect) throws SQLException {return enqueue(id,effect,0);}
  synchronized Receipt enqueue(String id, String effect,int cheese) throws SQLException {return enqueue(id,effect,cheese,null);}
  synchronized Receipt enqueue(String id, String effect,int cheese,String donor) throws SQLException {
    // Accept old stored tier metadata unchanged, including legacy state imports.
    // The HTTP boundary accepts only current tiers and excludes new mob events.
    if(cheese!=0 && cheese!=DonationNotice.amount(effect)
        && !(cheese==2000 && effect.equals("mob"))
        && !(cheese==5000 && (effect.equals("surface") || effect.equals("chancekill"))))throw new IllegalArgumentException("Invalid cheese amount");
    if (!id.matches("[A-Za-z0-9_-]{1,100}") || !EFFECTS.contains(effect)) throw new IllegalArgumentException("Invalid event");
    return transaction(() -> {
      try (PreparedStatement q = db.prepareStatement("SELECT effect FROM events WHERE id=?")) {
        q.setString(1,id);
        try (ResultSet r = q.executeQuery()) {
          if (r.next()) return r.getString(1)==null || effect.equals(r.getString(1)) ? Receipt.DUPLICATE : Receipt.CONFLICT;
        }
      }
      insert(id,effect,"PENDING");
      try(PreparedStatement update=db.prepareStatement("UPDATE events SET cheese=?,donor=? WHERE id=?")){
        update.setInt(1,cheese);update.setString(2,cheese==0?null:DonationNotice.safeDonor(donor));update.setString(3,id);update.executeUpdate();
      }
      return Receipt.QUEUED;
    });
  }
  private void insert(String id,String effect,String state) throws SQLException {
    try (PreparedStatement s = db.prepareStatement("INSERT INTO events(id,effect,state) VALUES(?,?,?)")) {
      s.setString(1,id);s.setString(2,effect);s.setString(3,state);s.executeUpdate();
    }
  }
  synchronized Event begin() throws SQLException {
    if (paused()) return null;
    return transaction(() -> {
      Event event;
      try (Statement s=db.createStatement();ResultSet r=s.executeQuery("SELECT id,effect,cheese,donor FROM events WHERE state='PENDING' ORDER BY rowid LIMIT 1")) {
        if (!r.next()) return null;
        event = new Event(r.getString(1),r.getString(2),r.getInt(3),r.getString(4));
      }
      transition(event.id(),"PENDING","RUNNING");
      return event;
    });
  }
  private void transition(String id,String from,String to) throws SQLException {
    try (PreparedStatement s=db.prepareStatement("UPDATE events SET state=?,donor=CASE WHEN ? IN ('DONE','UNCERTAIN') THEN NULL ELSE donor END WHERE id=? AND state=?")) {
      s.setString(1,to);s.setString(2,to);s.setString(3,id);s.setString(4,from);
      if (s.executeUpdate()!=1) throw new SQLException("Unexpected event state");
    }
  }
  synchronized void complete(String id) throws SQLException {
    transaction(() -> { transition(id,"RUNNING","DONE"); return null; });
  }
  synchronized void uncertain(String id) throws SQLException {
    transaction(() -> { transition(id,"RUNNING","UNCERTAIN");writePaused(true);return null; });
  }
  private void writePaused(boolean paused) throws SQLException {
    try (PreparedStatement s=db.prepareStatement("INSERT OR REPLACE INTO meta(key,value) VALUES('paused',?)")) {
      s.setString(1,Boolean.toString(paused));s.executeUpdate();
    }
  }
  synchronized void setPaused(boolean paused) throws SQLException {
    transaction(() -> {writePaused(paused);return null;});
  }
  synchronized boolean paused() throws SQLException {
    check();
    try (Statement s=db.createStatement();ResultSet r=s.executeQuery("SELECT value FROM meta WHERE key='paused'")) {
      return r.next() && Boolean.parseBoolean(r.getString(1));
    }
  }
  synchronized int count(String state) throws SQLException {
    check();
    try (PreparedStatement s=db.prepareStatement("SELECT count(*) FROM events WHERE state=?")) {
      s.setString(1,state);try(ResultSet r=s.executeQuery()){r.next();return r.getInt(1);}
    }
  }
  synchronized boolean needsMigration() throws SQLException {
    check();
    try (Statement s=db.createStatement();ResultSet r=s.executeQuery("SELECT 1 FROM meta WHERE key='legacyMigrated'")){return !r.next();}
  }
  synchronized void migrateLegacy(List<String> received,List<String> pending,boolean paused) throws SQLException {
    if (!needsMigration()) return;
    if (new HashSet<>(received).size()!=received.size() || received.stream().anyMatch(id->!id.matches("[A-Za-z0-9_-]{1,100}")) || pending.stream().anyMatch(e->!EFFECTS.contains(e)))
      throw new IllegalArgumentException("Invalid legacy state");
    transaction(() -> {
      for (String id:received) insert(id,null,"DONE");
      for (String effect:pending) insert("legacy_"+UUID.randomUUID().toString().replace("-",""),effect,"PENDING");
      writePaused(paused);
      try(Statement s=db.createStatement()){s.executeUpdate("INSERT INTO meta VALUES('legacyMigrated','true')");}
      return null;
    });
  }
  @Override public synchronized void close() {
    healthy=false;
    if(db!=null){try{db.close();}catch(SQLException ignored){}db=null;}
    if(fileLock!=null){try{fileLock.release();}catch(IOException ignored){}fileLock=null;}
    if(lockChannel!=null){try{lockChannel.close();}catch(IOException ignored){}lockChannel=null;}
  }
}
