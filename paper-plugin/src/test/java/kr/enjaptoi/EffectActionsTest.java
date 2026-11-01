package kr.enjaptoi;

import org.junit.jupiter.api.Test;
import org.bukkit.*;
import org.bukkit.entity.*;
import org.bukkit.inventory.*;
import java.lang.reflect.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class EffectActionsTest {
  @SuppressWarnings("unchecked") static <T>T proxy(Class<T> type,InvocationHandler h){return (T)Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},h);}
  static class Stack extends ItemStack {
    final Material type;final int amount;
    Stack(Material type,int amount){super();this.type=type;this.amount=amount;}
    @Override public Material getType(){return type;}
    @Override public int getAmount(){return amount;}
    @Override public ItemStack clone(){return new Stack(type,amount);}
    @Override public boolean isSimilar(ItemStack other){return other!=null && type==other.getType();}
  }
  static Random index(int index){return new Random(){@Override public int nextInt(int bound){assertTrue(index<bound);return index;}};}
  static class Scene {
    boolean dead,online=true,valid=true,spawnValid=true,dropValid=true,rejectDeath,throwOnDrop;
    double health=20;int inserted,spawnCalls,dropCalls,removals,killCalls;
    int leftoverAmount;int droppedAmount=-1;
    Map<Integer,ItemStack> slots=new HashMap<>();
    PlayerInventory inventory=proxy(PlayerInventory.class,(p,m,a)->switch(m.getName()){
      case "getSize"->41;
      case "getItem"->slots.get((int)a[0]);
      case "setItem"->{int slot=(int)a[0];if(a[1]==null){slots.remove(slot);removals++;}else slots.put(slot,(ItemStack)a[1]);yield null;}
      case "addItem"->{ItemStack item=((ItemStack[])a[0])[0];inserted+=item.getAmount()-leftoverAmount;yield leftoverAmount==0?new HashMap<Integer,ItemStack>():new HashMap<>(Map.of(0,new Stack(item.getType(),leftoverAmount)));}
      default->throw new UnsupportedOperationException(m.getName());
    });
    World world=proxy(World.class,(p,m,a)->switch(m.getName()){
      case "spawnEntity"->{spawnCalls++;yield proxy(Entity.class,(p2,m2,a2)->switch(m2.getName()){case "isValid"->spawnValid;case "isDead"->!spawnValid;default->throw new UnsupportedOperationException(m2.getName());});}
      case "dropItemNaturally"->{dropCalls++;if(throwOnDrop)throw new IllegalStateException("drop interrupted");ItemStack expected=(ItemStack)a[1];yield proxy(Item.class,(p2,m2,a2)->switch(m2.getName()){
        case "isValid"->dropValid;case "isDead"->!dropValid;
        case "getItemStack"->new Stack(expected.getType(),droppedAmount<0?expected.getAmount():droppedAmount);
        default->throw new UnsupportedOperationException(m2.getName());});}
      default->throw new UnsupportedOperationException(m.getName());
    });
    Player player=proxy(Player.class,(p,m,a)->switch(m.getName()){
      case "isOnline"->online;case "isValid"->valid;case "isDead"->dead;case "getHealth"->health;
      case "setHealth"->{killCalls++;if(!rejectDeath){health=(double)a[0];dead=health<=0;}yield null;}
      case "getInventory"->inventory;case "getWorld"->world;case "getLocation"->new Location(world,0,81,0);
      default->throw new UnsupportedOperationException(m.getName());
    });
  }
  @Test void killRequiresLivingTargetAndConfirmsResult(){
    Scene s=new Scene();s.dead=true;s.health=0;assertFalse(EffectActions.kill(s.player));assertEquals(0,s.killCalls);
    s.dead=false;s.health=20;s.rejectDeath=true;assertFalse(EffectActions.kill(s.player));
    s.rejectDeath=false;assertTrue(EffectActions.kill(s.player));assertEquals(0,s.health);
  }
  @Test void chanceKillHasExactlyFifteenWinningValuesOutOfHundred(){
    int wins=0;
    for(int roll=0;roll<100;roll++){Scene s=new Scene();if(EffectActions.chanceKill(s.player,index(roll)))wins++;}
    assertEquals(15,wins);
  }
  @Test void canceledSpawnAndMissingDestinationAreFailures(){
    Scene s=new Scene();assertFalse(EffectActions.spawn(s.player,null,EntityType.ZOMBIE));assertEquals(0,s.spawnCalls);
    s.spawnValid=false;assertFalse(EffectActions.spawn(s.player,new Location(s.world,0,81,0),EntityType.ZOMBIE));
    s.spawnValid=true;assertTrue(EffectActions.spawn(s.player,new Location(s.world,0,81,0),EntityType.ZOMBIE));
  }
  @Test void grantRequiresAllInventoryAndDropQuantities(){
    Scene s=new Scene();assertTrue(EffectActions.give(s.player,new Stack(Material.BREAD,5)));assertEquals(5,s.inserted);assertEquals(0,s.dropCalls);
    s=new Scene();s.leftoverAmount=3;assertTrue(EffectActions.give(s.player,new Stack(Material.BREAD,5)));assertEquals(2,s.inserted);assertEquals(1,s.dropCalls);
    s=new Scene();s.leftoverAmount=5;s.dropValid=false;assertFalse(EffectActions.give(s.player,new Stack(Material.BREAD,5)));assertEquals(0,s.inserted);
    s=new Scene();s.leftoverAmount=3;s.droppedAmount=1;assertFalse(EffectActions.give(s.player,new Stack(Material.BREAD,5)));assertEquals(2,s.inserted);
    s=new Scene();s.leftoverAmount=1;assertTrue(EffectActions.give(s.player,new Stack(Material.DIAMOND_PICKAXE,1)));assertEquals(0,s.inserted);
    s.dropValid=false;assertFalse(EffectActions.give(s.player,new Stack(Material.DIAMOND_PICKAXE,1)));
  }
  @Test void deletionCandidatesIncludeStorageHotbarArmorAndOffhandButNotOutsideInventory(){
    for(int chosen=0;chosen<7;chosen++){
      Scene s=new Scene();List<Integer> slots=List.of(0,20,36,37,38,39,40);
      for(int slot:slots)s.slots.put(slot,new Stack(Material.BREAD,64));
      s.slots.put(1,new Stack(Material.AIR,1));s.slots.put(2,new Stack(Material.BREAD,0));
      ItemStack outside=new Stack(Material.DIAMOND,12);s.slots.put(41,outside);
      assertTrue(EffectActions.clearOne(s.player,index(chosen)));assertNull(s.slots.get(slots.get(chosen)));assertEquals(1,s.removals);
      for(int i=0;i<slots.size();i++)if(i!=chosen)assertEquals(64,s.slots.get(slots.get(i)).getAmount());
      assertSame(outside,s.slots.get(41));
    }
  }
  @Test void emptyOrDeadInventoryNeverReportsDeletionSuccess(){
    Scene s=new Scene();assertFalse(EffectActions.clearOne(s.player,new Random()));assertEquals(0,s.removals);
    s.slots.put(40,new Stack(Material.BREAD,5));s.dead=true;assertFalse(EffectActions.clearOne(s.player,new Random()));assertEquals(0,s.removals);
  }
}
