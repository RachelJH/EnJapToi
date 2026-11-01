package kr.enjaptoi;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.util.*;
import org.junit.jupiter.api.Test;
import java.lang.reflect.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class SafeTeleportTest {
  @SuppressWarnings("unchecked") static <T>T proxy(Class<T> type,InvocationHandler h){return (T)Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},h);}
  static class Scene {
    boolean loaded=true,border=true;World.Environment environment=World.Environment.NORMAL;
    Map<String,Material> blocks=new HashMap<>();
    Map<String,Collection<BoundingBox>> shapes=new HashMap<>();
    World world=proxy(World.class,(p,m,a)->switch(m.getName()){
      case "getEnvironment"->environment;
      case "getMinHeight"->-64;
      case "getMaxHeight","getLogicalHeight"->320;
      case "isChunkLoaded"->loaded;
      case "getHighestBlockYAt"->80;
      case "getWorldBorder"->proxy(WorldBorder.class,(p2,m2,a2)->{if(m2.getName().equals("isInside"))return border;throw new UnsupportedOperationException(m2.getName());});
      case "getBlockAt"->block((int)a[0],(int)a[1],(int)a[2]);
      default->throw new UnsupportedOperationException(m.getName());
    });
    Block block(int x,int y,int z){
      Material material=blocks.getOrDefault(x+","+y+","+z,y==80?Material.STONE:Material.AIR);
      return proxy(Block.class,(p,m,a)->switch(m.getName()){
        case "getType"->material;
        case "isLiquid"->material==Material.WATER || material==Material.LAVA;
        case "getCollisionShape"->proxy(VoxelShape.class,(p2,m2,a2)->{
          if(m2.getName().equals("getBoundingBoxes"))return shapes.getOrDefault(x+","+y+","+z,material==Material.STONE?List.of(new BoundingBox(0,0,0,1,1,1)):List.of());
          throw new UnsupportedOperationException(m2.getName());
        });
        default->throw new UnsupportedOperationException(m.getName());
      });
    }
    Player player(double y){return proxy(Player.class,(p,m,a)->switch(m.getName()){
      case "getLocation"->new Location(world,-1.1,y,8.9,13,29);
      case "getWorld"->world;
      case "getBoundingBox"->new BoundingBox(-1.4,y,8.6,-.8,y+1.8,9.2);
      default->throw new UnsupportedOperationException(m.getName());
    });}
  }
  @Test void surfaceFromCaveAndAirPreservesCoordinatesAndView() {
    Scene s=new Scene();
    for(double y:new double[]{-20,250}){
      Location at=SafeTeleport.destination(s.player(y),true,new Random(1));assertNotNull(at);
      assertEquals(-1.1,at.getX());assertEquals(8.9,at.getZ());assertEquals(81,at.getY());
      assertEquals(13,at.getYaw());assertEquals(29,at.getPitch());assertSame(s.world,at.getWorld());
    }
  }
  @Test void entireFootprintNeedsSupportAndBodySpace() {
    Scene s=new Scene();s.blocks.put("-1,80,9",Material.AIR); // second block under edge of player's body
    assertNull(SafeTeleport.destination(s.player(0),true,new Random(1)));
    s.blocks.clear();s.blocks.put("-1,82,9",Material.STONE);
    assertNull(SafeTeleport.destination(s.player(0),true,new Random(1)));
    s.blocks.clear();s.shapes.put("-3,81,8",List.of(new BoundingBox(1,0,0,2,1,1)));
    assertNull(SafeTeleport.destination(s.player(0),true,new Random(1))); // adjacent moving block protrudes into body
  }
  @Test void nearbyHazardUnloadedChunkOrBorderStopsTeleport() {
    Scene s=new Scene();s.blocks.put("-3,80,8",Material.LAVA);
    assertNull(SafeTeleport.destination(s.player(0),true,new Random(1)));
    s.blocks.clear();s.loaded=false;assertNull(SafeTeleport.destination(s.player(0),true,new Random(1)));
    s.loaded=true;s.border=false;assertNull(SafeTeleport.destination(s.player(0),true,new Random(1)));
  }
  @Test void surfaceCannotSelectNetherRoofOrEndIsland() {
    Scene s=new Scene();
    for(var dimension:List.of(World.Environment.NETHER,World.Environment.THE_END)){
      s.environment=dimension;assertNull(SafeTeleport.destination(s.player(0),true,new Random(1)));
    }
  }
}
