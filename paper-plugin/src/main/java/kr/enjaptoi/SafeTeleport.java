package kr.enjaptoi;

import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.util.BoundingBox;
import java.util.Collection;
import java.util.Random;

final class SafeTeleport {
  static boolean fullCube(Collection<BoundingBox> shapes) {
    return shapes.stream().anyMatch(b->b.getMinX()<=0 && b.getMinY()<=0 && b.getMinZ()<=0
        && b.getMaxX()>=1 && b.getMaxY()==1 && b.getMaxZ()>=1);
  }
  static Location destination(Player player,boolean surface,Random random) {
    Location origin=player.getLocation();World world=player.getWorld();
    double half=Math.max(0.3,Math.max(player.getBoundingBox().getWidthX(),player.getBoundingBox().getWidthZ())/2);
    double height=Math.max(1.8,player.getBoundingBox().getHeight());
    TeleportPlanner.Terrain terrain=new TeleportPlanner.Terrain() {
      public int minY(){return world.getMinHeight();}
      public int maxY(){return world.getEnvironment()==World.Environment.NETHER?Math.min(world.getMaxHeight(),world.getLogicalHeight()):world.getMaxHeight();}
      public boolean overworld(){return world.getEnvironment()==World.Environment.NORMAL;}
      public int surface(int x,int z){
        if(!world.isChunkLoaded(x>>4,z>>4))return world.getMinHeight();
        return world.getHighestBlockYAt(x,z,HeightMap.MOTION_BLOCKING);
      }
      public boolean safe(double x,int y,double z) {
        if(y<=minY() || y+height>=maxY())return false;
        for(double dx:new double[]{-half,half})for(double dz:new double[]{-half,half})
          if(!world.getWorldBorder().isInside(new Location(world,x+dx,y,z+dz)))return false;
        BoundingBox body=new BoundingBox(x-half,y,z-half,x+half,y+height,z+half);
        int minX=(int)Math.floor(x-half),maxX=(int)Math.floor(x+half-1e-7);
        int minZ=(int)Math.floor(z-half),maxZ=(int)Math.floor(z+half-1e-7);
        for(int bx=minX-1;bx<=maxX+1;bx++)for(int bz=minZ-1;bz<=maxZ+1;bz++) {
          if(!world.isChunkLoaded(bx>>4,bz>>4))return false;
          for(int by=y-1;by<Math.ceil(y+height);by++) {
            Block block=world.getBlockAt(bx,by,bz);
            if(TeleportPlanner.hazardous(block.getType().name()) || block.isLiquid())return false;
            Collection<BoundingBox> shapes=block.getCollisionShape().getBoundingBoxes();
            if(by==y-1 && bx>=minX && bx<=maxX && bz>=minZ && bz<=maxZ && !fullCube(shapes))return false;
            // Check neighboring shapes too: a collision may extend outside its own block.
            for(BoundingBox shape:shapes)if(shape.clone().shift(bx,by,bz).overlaps(body))return false;
          }
        }
        return true;
      }
    };
    TeleportPlanner.Point point=surface?TeleportPlanner.surface(terrain,origin.getX(),origin.getZ()):TeleportPlanner.chorus(terrain,origin.getX(),origin.getBlockY(),origin.getZ(),random);
    return point==null?null:new Location(world,point.x(),point.y(),point.z(),origin.getYaw(),origin.getPitch());
  }
}
