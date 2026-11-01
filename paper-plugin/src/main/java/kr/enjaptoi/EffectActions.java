package kr.enjaptoi;

import java.util.*;
import org.bukkit.Location;
import org.bukkit.entity.*;
import org.bukkit.inventory.*;

/** Immediate effect outcomes. Partial delivery is never retried or rolled back automatically. */
final class EffectActions {
  static boolean ready(Player player){return player!=null && player.isOnline() && player.isValid() && !player.isDead() && player.getHealth()>0;}
  static boolean kill(Player player){
    if(!ready(player))return false;
    player.setHealth(0.0);
    return player.isDead() || player.getHealth()<=0;
  }
  static boolean chanceKill(Player player,Random random){return ready(player) && random.nextInt(100)<15 && kill(player);}
  static boolean spawn(Player player,Location at,EntityType type){
    if(!ready(player) || at==null)return false;
    Entity spawned=player.getWorld().spawnEntity(at,type);
    return spawned!=null && spawned.isValid() && !spawned.isDead();
  }
  static boolean give(Player player,ItemStack item){
    if(!ready(player))return false;
    Map<Integer,ItemStack> leftovers=player.getInventory().addItem(item.clone());
    boolean complete=true;
    for(ItemStack leftover:leftovers.values()){
      ItemStack expected=leftover.clone();
      Item dropped=player.getWorld().dropItemNaturally(player.getLocation(),leftover.clone());
      if(dropped==null || !dropped.isValid() || dropped.isDead()
          || !expected.isSimilar(dropped.getItemStack()) || dropped.getItemStack().getAmount()<expected.getAmount())complete=false;
    }
    // addItem reports uninserted quantities. Success requires every remainder to exist as a valid drop.
    // If part succeeded, keep it and report failure: refund/retry could duplicate already-delivered items.
    return complete;
  }
  static boolean empty(ItemStack item){return item==null || item.getAmount()<=0 || (item.getType()==org.bukkit.Material.AIR || item.getType()==org.bukkit.Material.CAVE_AIR || item.getType()==org.bukkit.Material.VOID_AIR);}
  static boolean clearOne(Player player,Random random){
    if(!ready(player))return false;
    PlayerInventory inventory=player.getInventory();List<Integer> candidates=new ArrayList<>();
    // PlayerInventory: 0..35 storage/hotbar, 36..39 armor, 40 offhand. Never touch cursor/containers.
    for(int slot=0;slot<Math.min(41,inventory.getSize());slot++)if(!empty(inventory.getItem(slot)))candidates.add(slot);
    if(candidates.isEmpty())return false;
    int slot=candidates.get(random.nextInt(candidates.size()));
    inventory.setItem(slot,null); // Remove this entire stack, leaving every other slot alone.
    return empty(inventory.getItem(slot));
  }
}
