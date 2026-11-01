package kr.enjaptoi;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class EventRunnerTest {
  @TempDir Path dir;
  @Test void deathLeavesQueuePendingAndRespawnResumesInOrderAtThreeSecondIntervals()throws Exception{
    try(EventStore store=new EventStore(dir.resolve("queue.db"))){
      store.enqueue("first","kill",30000);store.enqueue("second","bread",1000);store.enqueue("third","move",1000);
      EventRunner runner=new EventRunner();EffectActionsTest.Scene s=new EffectActionsTest.Scene();List<String> executed=new ArrayList<>();
      s.dead=true;s.health=0;
      assertFalse(runner.run(store,s.player,10000,3000,e->{fail("dead target executed");return true;},c->fail("dead target notice")));
      assertEquals(3,store.count("PENDING"));assertEquals(0,store.count("RUNNING"));assertEquals(0,store.count("DONE"));
      s.dead=false;s.health=20;
      assertTrue(runner.run(store,s.player,11000,3000,e->{executed.add(e.id());return EffectActions.kill(s.player);},c->{}));
      assertFalse(runner.run(store,s.player,18000,3000,e->{fail("respawn not complete");return true;},c->fail("dead notice")));
      assertEquals(2,store.count("PENDING"));
      s.dead=false;s.health=20;
      assertTrue(runner.run(store,s.player,19000,3000,e->{executed.add(e.id());return true;},c->{}));
      assertFalse(runner.run(store,s.player,21999,3000,e->{fail("cooldown");return true;},c->{}));
      assertTrue(runner.run(store,s.player,22000,3000,e->{executed.add(e.id());return true;},c->{}));
      assertEquals(List.of("first","second","third"),executed);
    }
  }
  @Test void partialGrantIsNotAnnouncedOrRepeatedOnDuplicateOrRestart()throws Exception{
    Path db=dir.resolve("partial.db");EffectActionsTest.Scene s=new EffectActionsTest.Scene();s.leftoverAmount=3;s.dropValid=false;
    try(EventStore store=new EventStore(db)){
      store.enqueue("id","bread",1000,"홍길동");
      assertTrue(new EventRunner().run(store,s.player,10000,3000,e->EffectActions.give(s.player,new EffectActionsTest.Stack(org.bukkit.Material.BREAD,5)),c->fail("partial grant notice")));
      assertEquals(2,s.inserted);assertEquals(1,s.dropCalls);assertEquals(1,store.count("DONE"));
      assertEquals(EventStore.Receipt.DUPLICATE,store.enqueue("id","bread",1000));
    }
    try(EventStore store=new EventStore(db)){
      assertFalse(new EventRunner().run(store,s.player,20000,3000,e->{fail("duplicate grant");return true;},c->fail("duplicate notice")));
    }
    assertEquals(2,s.inserted);assertEquals(1,s.dropCalls);
  }
  @Test void exceptionAfterPartialInsertionIsHeldUncertainInsteadOfRetried()throws Exception{
    Path db=dir.resolve("uncertain.db");EffectActionsTest.Scene s=new EffectActionsTest.Scene();s.leftoverAmount=3;s.throwOnDrop=true;
    try(EventStore store=new EventStore(db)){
      store.enqueue("id","bread",1000);
      assertThrows(IllegalStateException.class,()->new EventRunner().run(store,s.player,10000,3000,e->EffectActions.give(s.player,new EffectActionsTest.Stack(org.bukkit.Material.BREAD,5)),c->fail("interrupted notice")));
      assertEquals(1,store.count("UNCERTAIN"));assertTrue(store.paused());
    }
    try(EventStore store=new EventStore(db)){assertNull(store.begin());assertEquals(1,store.count("UNCERTAIN"));}
    assertEquals(2,s.inserted);assertEquals(1,s.dropCalls);
  }
  @Test void canceledMobAndEmptyDeletionHaveNoCompletionNotice()throws Exception{
    try(EventStore store=new EventStore(dir.resolve("failures.db"))){
      EffectActionsTest.Scene s=new EffectActionsTest.Scene();s.spawnValid=false;EventRunner runner=new EventRunner();
      store.enqueue("mob","mob",2000);store.enqueue("clear","clear",5000);
      assertTrue(runner.run(store,s.player,10000,3000,e->EffectActions.spawn(s.player,new org.bukkit.Location(s.world,0,81,0),org.bukkit.entity.EntityType.ZOMBIE),c->fail("canceled mob notice")));
      assertTrue(runner.run(store,s.player,13000,3000,e->EffectActions.clearOne(s.player,new Random()),c->fail("empty inventory notice")));
      assertEquals(2,store.count("DONE"));
    }
  }
  @Test void quickRespawnDoesNotResetThePreviousExecutionCooldown()throws Exception{
    try(EventStore store=new EventStore(dir.resolve("quick.db"))){
      store.enqueue("kill","kill",30000);store.enqueue("next","bread",1000);
      EffectActionsTest.Scene s=new EffectActionsTest.Scene();EventRunner runner=new EventRunner();
      assertTrue(runner.run(store,s.player,10000,3000,e->EffectActions.kill(s.player),c->{}));
      s.dead=false;s.health=20;
      assertFalse(runner.run(store,s.player,11000,3000,e->{fail("early respawn execution");return true;},c->{}));
      assertEquals(1,store.count("PENDING"));
      assertTrue(runner.run(store,s.player,13000,3000,e->{assertEquals("next",e.id());return true;},c->{}));
    }
  }

}
