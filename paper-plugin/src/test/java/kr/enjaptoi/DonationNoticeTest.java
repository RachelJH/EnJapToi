package kr.enjaptoi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import net.kyori.adventure.text.*;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.jupiter.api.Assertions.*;
class DonationNoticeTest {
  @TempDir Path dir;
  @Test void onlyKnownCheeseHasLiteralAnonymousNotice() {
    assertEquals("\"익명의 후원자\"님이 \"1,000치즈\"를 후원하셨습니다! (후렴과 효과)",((TextComponent)DonationNotice.message("move",1000)).content());
    assertNull(DonationNotice.message("move",0));assertNull(DonationNotice.message("move",5000));
    assertEquals(5000,DonationNotice.amount("surface"));assertEquals(30000,DonationNotice.amount("kill"));
  }
  @Test void successfulNoticeOnceAfterDurableCompletionAndMetadataSurvivesRestart() throws Exception {
    Path db=dir.resolve("events.db");List<Component> notices=new ArrayList<>();
    try(EventStore s=new EventStore(db)){s.enqueue("id","surface",5000);}
    try(EventStore s=new EventStore(db)){
      var event=s.begin();assertEquals(5000,event.cheese());DonationNotice.complete(s,event,true,notices::add);
      assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("id","surface",5000));assertNull(s.begin());
    }
    try(EventStore s=new EventStore(db)){assertNull(s.begin());}
    assertEquals(1,notices.size());
  }
  @Test void failedEffectOrUnknownLegacyAmountDoesNotAnnounce() throws Exception {
    try(EventStore s=new EventStore(dir.resolve("events.db"))){
      s.enqueue("failed","move",1000);DonationNotice.complete(s,s.begin(),false,c->fail("failed effect"));
      s.enqueue("legacy","bread");DonationNotice.complete(s,s.begin(),true,c->fail("unverified amount"));
      assertEquals(2,s.count("DONE"));
    }
  }
  @Test void failedDoneCommitHasNoNoticeAndRestartHoldsUncertain() throws Exception {
    Path db=dir.resolve("events.db");AtomicBoolean fail=new AtomicBoolean();
    try(EventStore s=new EventStore(db,c->{if(fail.get())throw new SQLException("disk failure");c.commit();})){
      s.enqueue("id","move",1000);var event=s.begin();fail.set(true);
      assertThrows(SQLException.class,()->DonationNotice.complete(s,event,true,c->fail("uncommitted notice")));
    }
    try(EventStore s=new EventStore(db)){assertNull(s.begin());assertEquals(1,s.count("UNCERTAIN"));}
  }
  @Test void oldDatabaseUpgradesWithoutInventingCheese() throws Exception {
    Path db=dir.resolve("old.db");
    try(var c=java.sql.DriverManager.getConnection("jdbc:sqlite:"+db);var st=c.createStatement()){
      st.execute("CREATE TABLE events(id TEXT PRIMARY KEY,effect TEXT,state TEXT)");st.execute("INSERT INTO events VALUES('old','bread','PENDING')");
    }
    try(EventStore s=new EventStore(db)){assertEquals(0,s.begin().cheese());}
  }
}
