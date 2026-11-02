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
    assertEquals(3000,DonationNotice.amount("surface"));assertEquals(30000,DonationNotice.amount("kill"));
    assertEquals(4000,DonationNotice.amount("chancekill"));
    assertNotNull(DonationNotice.message("surface",3000));assertNotNull(DonationNotice.message("chancekill",4000));
    assertNull(DonationNotice.message("mob",2000));
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
      s.enqueue("id","move",1000,"홍길동");var event=s.begin();fail.set(true);
      assertThrows(SQLException.class,()->DonationNotice.complete(s,event,true,c->fail("uncommitted notice")));
    }
    try(EventStore s=new EventStore(db)){assertNull(s.begin());assertEquals(1,s.count("UNCERTAIN"));}
  }
  @Test void oldDatabaseUpgradesWithoutInventingCheese() throws Exception {
    Path db=dir.resolve("old.db");
    try(var c=java.sql.DriverManager.getConnection("jdbc:sqlite:"+db);var st=c.createStatement()){
      st.execute("CREATE TABLE events(id TEXT PRIMARY KEY,effect TEXT,state TEXT)");st.execute("INSERT INTO events VALUES('old','bread','PENDING')");
    }
    try(EventStore s=new EventStore(db)){var event=s.begin();assertEquals(0,event.cheese());assertNull(event.donor());}
  }
  @Test void namedAndAnonymousFormatsHavePlainSafeTextOnly() {
    var named=(TextComponent)DonationNotice.message("move",1000,"홍길동");
    assertEquals("\"홍길동\"님이 \"1,000치즈\"를 후원하셨습니다! (후렴과 효과)",named.content());
    assertNull(named.clickEvent());assertNull(named.hoverEvent());assertTrue(named.children().isEmpty());
    assertEquals("\"익명의 후원자\"님이 \"5,000치즈\"를 후원하셨습니다! (지상이동)",((TextComponent)DonationNotice.message("surface",5000,null)).content());
    for(String unsafe:List.of("", "익명", "Anonymous", "§a관리자", "&a관리자", "홍\n길동", "홍\r길동", "홍\t길동", "홍\u202e길동", "홍\u200b길동", "홍\u2028길동", "<click:run_command:/op>", "홍\"길동", "/op admin", "A".repeat(33), "\ud800")){
      assertNull(DonationNotice.safeDonor(unsafe));
      assertTrue(((TextComponent)DonationNotice.message("move",1000,unsafe)).content().startsWith("\"익명의 후원자\""));
    }
    for(String safe:List.of("홍길동", "Donor_123", "김 후원자", "Cafe\u0301", "A".repeat(32)))assertEquals(safe,DonationNotice.safeDonor(safe));
    assertNull(DonationNotice.message("move",5000,"홍길동"));
  }
  @Test void namedReceiptSurvivesRestartAndDuplicateCannotReplaceIdentity() throws Exception {
    Path db=dir.resolve("named.db");List<Component> notices=new ArrayList<>();
    try(EventStore s=new EventStore(db)){
      s.enqueue("id","move",1000,"홍길동");
      assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("id","move",1000,"다른이름"));
    }
    try(EventStore s=new EventStore(db)){
      var event=s.begin();assertEquals("홍길동",event.donor());assertFalse(event.toString().contains("홍길동"));
      DonationNotice.complete(s,event,true,notices::add);
    }
    try(EventStore s=new EventStore(db)){assertNull(s.begin());assertEquals(EventStore.Receipt.DUPLICATE,s.enqueue("id","move",1000,"다른이름"));}
    assertEquals(1,notices.size());assertTrue(((TextComponent)notices.getFirst()).content().contains("홍길동"));
    try(var c=java.sql.DriverManager.getConnection("jdbc:sqlite:"+db);var st=c.createStatement();var r=st.executeQuery("SELECT donor FROM events")){assertTrue(r.next());assertNull(r.getString(1));}
  }
  @Test void interruptedNamedExecutionIsHeldAndNameIsRemoved() throws Exception {
    Path db=dir.resolve("interrupted.db");
    try(EventStore s=new EventStore(db)){s.enqueue("id","move",1000,"홍길동");s.begin();}
    try(EventStore s=new EventStore(db)){assertNull(s.begin());assertEquals(1,s.count("UNCERTAIN"));}
    try(var c=java.sql.DriverManager.getConnection("jdbc:sqlite:"+db);var st=c.createStatement();var r=st.executeQuery("SELECT donor FROM events")){assertTrue(r.next());assertNull(r.getString(1));}
  }

}
