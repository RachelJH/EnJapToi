package kr.enjaptoi;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.jupiter.api.Assertions.*;

class EventStoreTest {
  @TempDir Path temp;
  Path path(){return temp.resolve("events.sqlite3");}

  @Test void receiptIsCommittedBeforeAckAndDuplicateSurvivesRestart() throws Exception {
    try(EventStore s=new EventStore(path())) {
      assertEquals(EventStore.Receipt.QUEUED,s.enqueue("id1","bread"));
      try(Connection observer=DriverManager.getConnection("jdbc:sqlite:"+path());Statement q=observer.createStatement();ResultSet r=q.executeQuery("SELECT count(*) FROM events WHERE id='id1' AND state='PENDING'")) {
        assertTrue(r.next());assertEquals(1,r.getInt(1));
      }
    }
    try(EventStore s=new EventStore(path())) {
      assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("id1","bread"));assertEquals(1,s.count("PENDING"));
      assertEquals(EventStore.Receipt.CONFLICT,s.enqueue("id1","kill"));
    }
  }
  @Test void failureBeforeCommitNeverAcknowledgesOrKeepsGhostId() throws Exception {
    AtomicBoolean fail=new AtomicBoolean();
    try(EventStore s=new EventStore(path(),c->{if(fail.get())throw new SQLException("disk failure");c.commit();})) {
      fail.set(true);
      assertThrows(SQLException.class,()->s.enqueue("retry","bread"));
      assertThrows(SQLException.class,()->s.enqueue("retry","bread")); // fail closed, not duplicate
    }
    try(EventStore s=new EventStore(path())) {
      assertEquals(0,s.count("PENDING"));assertEquals(EventStore.Receipt.QUEUED,s.enqueue("retry","bread"));
    }
  }
  @Test void ambiguousCommitCanBeRetriedWithSameIdAfterRestart() throws Exception {
    AtomicBoolean fail=new AtomicBoolean();
    try(EventStore s=new EventStore(path(),c->{c.commit();if(fail.get())throw new SQLException("lost commit confirmation");})) {
      fail.set(true);assertThrows(SQLException.class,()->s.enqueue("retry","bread"));
    }
    try(EventStore s=new EventStore(path())) {
      assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("retry","bread"));assertEquals(1,s.count("PENDING"));
    }
  }
  @Test void pendingQueueAndPauseSurviveRestartInOrder() throws Exception {
    try(EventStore s=new EventStore(path())) {s.enqueue("a","bread");s.enqueue("b","buff");s.setPaused(true);assertNull(s.begin());}
    try(EventStore s=new EventStore(path())) {
      assertTrue(s.paused());assertNull(s.begin());s.setPaused(false);
      EventStore.Event a=s.begin();assertEquals("a",a.id());s.complete(a.id());
      assertEquals("b",s.begin().id());
    }
  }
  @Test void crashAfterIntentIsHeldUncertainAndPausedNotReplayed() throws Exception {
    try(EventStore s=new EventStore(path())) {s.enqueue("a","bread");assertEquals("a",s.begin().id());}
    try(EventStore s=new EventStore(path())) {
      assertEquals(1,s.count("UNCERTAIN"));assertTrue(s.paused());assertNull(s.begin());
      s.setPaused(false);assertNull(s.begin());assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("a","bread"));
    }
  }
  @Test void completedEventNeverReappearsAfterRestart() throws Exception {
    try(EventStore s=new EventStore(path())) {s.enqueue("a","bread");s.complete(s.begin().id());}
    try(EventStore s=new EventStore(path())) {assertEquals(1,s.count("DONE"));assertNull(s.begin());assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("a","bread"));}
  }
  @Test void failureToPersistIntentDoesNotReleaseAnEventForExecution() throws Exception {
    AtomicBoolean fail=new AtomicBoolean();
    try(EventStore s=new EventStore(path(),c->{if(fail.get())throw new SQLException("disk failure");c.commit();})) {
      s.enqueue("a","bread");fail.set(true);assertThrows(SQLException.class,s::begin);
    }
    try(EventStore s=new EventStore(path())) {assertEquals(1,s.count("PENDING"));assertEquals(0,s.count("UNCERTAIN"));}
  }
  @Test void failureAfterEffectBeforeCompletionIsHeldNotAutomaticallyRetried() throws Exception {
    AtomicBoolean fail=new AtomicBoolean();
    try(EventStore s=new EventStore(path(),c->{if(fail.get())throw new SQLException("disk failure");c.commit();})) {
      s.enqueue("a","bread");EventStore.Event a=s.begin();fail.set(true);assertThrows(SQLException.class,()->s.complete(a.id()));
    }
    try(EventStore s=new EventStore(path())) {assertEquals(1,s.count("UNCERTAIN"));assertNull(s.begin());}
  }
  @Test void runtimeFailureCanBeMarkedUncertainWithoutLosingReceipt() throws Exception {
    try(EventStore s=new EventStore(path())) {s.enqueue("a","bread");s.uncertain(s.begin().id());assertTrue(s.paused());assertEquals(1,s.count("UNCERTAIN"));}
  }
  @Test void legacyMigrationIsAtomicAndIdempotent() throws Exception {
    try(EventStore s=new EventStore(path())) {
      s.migrateLegacy(List.of("old-id"),List.of("bread","buff"),true);
      s.migrateLegacy(List.of("old-id"),List.of("bread","buff"),false);
      assertEquals(2,s.count("PENDING"));assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("old-id","bread"));assertTrue(s.paused());
    }
    try(EventStore s=new EventStore(path())) {assertFalse(s.needsMigration());assertEquals(2,s.count("PENDING"));}
  }
  @Test void failedMigrationCanRestartWithoutPartialImport() throws Exception {
    AtomicBoolean fail=new AtomicBoolean();
    try(EventStore s=new EventStore(path(),c->{if(fail.get())throw new SQLException("disk failure");c.commit();})) {
      fail.set(true);assertThrows(SQLException.class,()->s.migrateLegacy(List.of("old-id"),List.of("bread"),false));
    }
    try(EventStore s=new EventStore(path())) {assertTrue(s.needsMigration());assertEquals(0,s.count("PENDING"));s.migrateLegacy(List.of("old-id"),List.of("bread"),false);assertEquals(1,s.count("PENDING"));}
  }
  @Test void invalidLegacyAndConcurrentStoreFailClosed() throws Exception {
    try(EventStore s=new EventStore(path())) {
      assertThrows(IllegalArgumentException.class,()->s.migrateLegacy(List.of("bad id"),List.of("bread"),false));
      assertThrows(java.io.IOException.class,()->new EventStore(path()));
    }
  }
  void crashProcess(String mode) throws Exception {
    String javaExe=Path.of(System.getProperty("java.home"),"bin",System.getProperty("os.name").startsWith("Windows")?"java.exe":"java").toString();
    String cp=System.getProperty("surefire.test.class.path",System.getProperty("java.class.path"));
    Process process=new ProcessBuilder(javaExe,"-cp",cp,"kr.enjaptoi.StoreCrashProbe",path().toString(),mode).redirectErrorStream(true).redirectOutput(temp.resolve("probe.log").toFile()).start();
    try {assertTrue(process.waitFor(15,java.util.concurrent.TimeUnit.SECONDS));assertEquals(0,process.exitValue());}
    finally {if(process.isAlive())process.destroyForcibly();}
  }
  @Test void hardExitAfterReceiptPreservesPendingAndDeduplication() throws Exception {
    crashProcess("receipt");
    try(EventStore s=new EventStore(path())) {assertEquals(1,s.count("PENDING"));assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("crash-id","bread"));}
  }
  @Test void hardExitAfterIntentHoldsUncertainWithoutReexecution() throws Exception {
    crashProcess("intent");
    try(EventStore s=new EventStore(path())) {assertEquals(1,s.count("UNCERTAIN"));assertTrue(s.paused());assertNull(s.begin());}
  }

}
