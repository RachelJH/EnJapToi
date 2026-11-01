package kr.enjaptoi;

import java.util.Random;

/** Pure search policy; terrain safety is supplied by the Bukkit adapter. */
final class TeleportPlanner {
  record Point(double x,int y,double z) {}
  interface Terrain {
    int minY(); int maxY(); boolean overworld();
    int surface(int x,int z);
    boolean safe(double x,int y,double z);
  }
  static Point surface(Terrain terrain,double x,double z) {
    if(!terrain.overworld())return null; // Nether roof/caverns and custom dimensions are ambiguous.
    int y=terrain.surface((int)Math.floor(x),(int)Math.floor(z))+1;
    return y>terrain.minY() && y<terrain.maxY()-1 && terrain.safe(x,y,z)?new Point(x,y,z):null;
  }
  static Point chorus(Terrain terrain,double x,int y,double z,Random random) {
    for(int attempt=0;attempt<64;attempt++) {
      double angle=random.nextDouble()*Math.PI*2;
      double radius=Math.sqrt(random.nextDouble())*50;
      double targetX=Math.floor(x+Math.cos(angle)*radius)+0.5;
      double targetZ=Math.floor(z+Math.sin(angle)*radius)+0.5;
      if(Math.pow(targetX-x,2)+Math.pow(targetZ-z,2)>2500)continue;
      int top=Math.min(terrain.maxY()-2,y+16),bottom=Math.max(terrain.minY()+1,y-32);
      for(int targetY=top;targetY>=bottom;targetY--)
        if(terrain.safe(targetX,targetY,targetZ))return new Point(targetX,targetY,targetZ);
    }
    return null;
  }
  static boolean hazardous(String type) {
    return switch(type) {
      case "WATER","LAVA","FIRE","SOUL_FIRE","MAGMA_BLOCK","CACTUS","SWEET_BERRY_BUSH",
           "WITHER_ROSE","POWDER_SNOW","POINTED_DRIPSTONE","CAMPFIRE","SOUL_CAMPFIRE",
           "NETHER_PORTAL","END_PORTAL","END_GATEWAY","TRIPWIRE","SAND","RED_SAND","GRAVEL" -> true;
      default -> type.endsWith("_PRESSURE_PLATE") || type.endsWith("_LEAVES");
    };
  }
}
