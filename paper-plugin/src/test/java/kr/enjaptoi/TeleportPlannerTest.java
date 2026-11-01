package kr.enjaptoi;
import org.junit.jupiter.api.Test;
import org.bukkit.util.BoundingBox;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class TeleportPlannerTest {
  static class Ground implements TeleportPlanner.Terrain {
    boolean normal=true,available=true;int top=80;int checked;
    public int minY(){return -64;} public int maxY(){return 320;}
    public boolean overworld(){return normal;}
    public int surface(int x,int z){assertEquals(-2,x);assertEquals(8,z);return top;}
    public boolean safe(double x,int y,double z){checked++;return available && y==81;}
  }
  @Test void chorusStaysInFiftyBlockCircleAndNeedsSafeGround() {
    Ground t=new Ground();
    for(int seed=0;seed<1000;seed++) {
      var p=TeleportPlanner.chorus(t,-1.9,70,8.125,new Random(seed));assertNotNull(p);
      assertTrue(Math.hypot(p.x()+1.9,p.z()-8.125)<=50);assertEquals(81,p.y());
    }
    t.available=false;assertNull(TeleportPlanner.chorus(t,0,70,0,new Random(1)));
    assertNull(TeleportPlanner.chorus(t,0,-64,0,new Random(1)));
  }
  @Test void surfacePreservesExactCoordinatesAndNeverFallsBackToCave() {
    Ground t=new Ground();var p=TeleportPlanner.surface(t,-1.9,8.125);
    assertEquals(-1.9,p.x());assertEquals(8.125,p.z());assertEquals(81,p.y());
    t.top=200;assertNull(TeleportPlanner.surface(t,-1.9,8.125)); // cave floor at 80 is not used
    t.top=320;assertNull(TeleportPlanner.surface(t,-1.9,8.125));
    t.normal=false;t.checked=0;assertNull(TeleportPlanner.surface(t,-1.9,8.125));assertEquals(0,t.checked);
  }
  @Test void unsafeSupportAndDamageBlocksAreRejected() {
    for(String type:List.of("LAVA","WATER","MAGMA_BLOCK","CACTUS","FIRE","POWDER_SNOW","OAK_LEAVES","STONE_PRESSURE_PLATE","SAND"))assertTrue(TeleportPlanner.hazardous(type),type);
    assertFalse(TeleportPlanner.hazardous("STONE"));
    assertTrue(SafeTeleport.fullCube(List.of(new BoundingBox(0,0,0,1,1,1))));
    assertFalse(SafeTeleport.fullCube(List.of(new BoundingBox(0,0,0,1,.5,1))));
    assertFalse(SafeTeleport.fullCube(List.of()));
  }
}
