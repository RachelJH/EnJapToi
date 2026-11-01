package kr.enjaptoi;

import com.sun.net.httpserver.HttpServer;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.command.*;
import org.bukkit.entity.*;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.Damageable;
import org.bukkit.potion.PotionEffect;
import org.bukkit.potion.PotionEffectType;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.scheduler.BukkitTask;
import net.kyori.adventure.text.Component;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.SecureRandom;
import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.*;

public class EnJapToi extends JavaPlugin implements CommandExecutor {
  private EventStore store;
  private ManagedReceiver managedReceiver;
  private final String serverInstance=UUID.randomUUID().toString();
  private boolean storageFailed;
  private final Random random = new SecureRandom();
  private HttpServer server;
  private BukkitTask ticker;
  private String token;
  private long lastExecution = 0;

  @Override public void onEnable() {
    saveDefaultConfig();
    try {
      store = new EventStore(getDataFolder().toPath().resolve("events.sqlite3"));
      migrateLegacyState();
      storageFailed=false;
      if (store.count("UNCERTAIN") > 0) getLogger().warning("Uncertain events require manual review; they are never replayed automatically.");
      File tokenFile = new File(getDataFolder(), "bridge-token.txt");
      if (!tokenFile.exists()) {
        byte[] bytes = new byte[32]; new SecureRandom().nextBytes(bytes);
        Files.writeString(tokenFile.toPath(), Base64.getUrlEncoder().withoutPadding().encodeToString(bytes), StandardCharsets.UTF_8);
      }
      token = Files.readString(tokenFile.toPath(), StandardCharsets.UTF_8).trim();
      server = HttpServer.create(new InetSocketAddress(getConfig().getString("listen-host", "127.0.0.1"), getConfig().getInt("listen-port",18765)), 0);
      server.createContext("/event", BridgeEndpoint.managed(token,serverInstance,(id,effect,cheese) ->
        Bukkit.getScheduler().callSyncMethod(this, () -> {
          try { return store.enqueue(id,effect,cheese); }
          catch(SQLException e) { storageFailed=true;throw e; }
        }).get(5,TimeUnit.SECONDS)));
      server.start();
    } catch(Exception e) { getLogger().severe("Local HTTP bridge failed: " + e.getMessage()); getServer().getPluginManager().disablePlugin(this); return; }
    Objects.requireNonNull(getCommand("ejt")).setExecutor(this);
    ticker = Bukkit.getScheduler().runTaskTimer(this, this::tick,20L,20L);
    startReceiver();
  }
  private void startReceiver() {
    if(!getConfig().getBoolean("receiver.enabled",false)) {
      getLogger().info("Automatic donation receiver disabled; configure receiver settings to enable.");return;
    }
    try {
      List<String> command=new ArrayList<>(List.of(
        getConfig().getString("receiver.python","python"),"-u",
        getConfig().getString("receiver.script",""),"--managed-stdin",
        "--channel-id",getConfig().getString("receiver.channel-id",""),
        "--donation-type",getConfig().getString("receiver.donation-type","CHAT"),
        "--amount-map",getConfig().getString("receiver.amount-map",""),
        "--token-file",new File(getDataFolder(),"bridge-token.txt").getAbsolutePath(),
        "--port",Integer.toString(getConfig().getInt("listen-port",18765))));
      String client=getConfig().getString("receiver.client-config","");
      if(!client.isBlank())command.addAll(List.of("--config",client));
      if(getConfig().getBoolean("receiver.enable-game-delivery",false))
        command.addAll(List.of("--enable-game-delivery","--verification-file",getConfig().getString("receiver.verification-file","")));
      managedReceiver=new ManagedReceiver(command,Map.of("EJT_SERVER_INSTANCE",serverInstance),new File(getDataFolder(),"receiver.log"));
      getLogger().info("Managed donation receiver started. See receiver.log for safe diagnostics.");
    } catch(Exception e){getLogger().severe("Managed receiver could not start. Check receiver paths; Paper remains available.");}
  }
  private void tick() {
    if (storageFailed) return;
    try {
      if (store.paused() || store.count("PENDING")==0) return;
      Player player=Bukkit.getPlayerExact(getConfig().getString("broadcaster", "Yirue"));
      if(player==null)return;
      long now=System.currentTimeMillis();
      if(now-lastExecution<getConfig().getLong("interval-ticks",60)*50)return;
      EventStore.Event event=store.begin();
      if(event==null)return;
      lastExecution=now;
      boolean applied;
      try { applied=executeEvent(player,event.effect()); }
      catch(RuntimeException e) {
        store.uncertain(event.id());
        getLogger().severe("Event execution interrupted; marked UNCERTAIN and paused. Review before resuming.");
        return;
      }
      DonationNotice.complete(store,event,applied,notice->Bukkit.broadcast(notice));
    } catch(SQLException e) {
      storageFailed=true;
      getLogger().severe("Event storage failed; execution stopped. Restart and review UNCERTAIN events.");
    }
  }
  private void migrateLegacyState() throws Exception {
    if(!store.needsMigration())return;
    File legacy=new File(getDataFolder(),"state.yml");
    if(!legacy.exists()){store.migrateLegacy(List.of(),List.of(),false);return;}
    YamlConfiguration y=new YamlConfiguration();
    y.load(legacy); // Strict parse: never silently replace damaged state with an empty queue.
    for(String key:List.of("received","pending")) {
      Object value=y.get(key);
      if(!(value instanceof List<?> list) || list.stream().anyMatch(item->!(item instanceof String)))
        throw new IOException("Invalid legacy state");
    }
    if(!y.isBoolean("paused"))throw new IOException("Invalid legacy pause state");
    store.migrateLegacy(y.getStringList("received"),y.getStringList("pending"),y.getBoolean("paused"));
    getLogger().info("Legacy state imported transactionally. Original state.yml retained; do not restore it over the database.");
  }
  @Override public void onDisable() {
    if(managedReceiver!=null)managedReceiver.close();
    if(ticker!=null)ticker.cancel();
    if(server!=null)server.stop(1);
    if(store!=null)store.close();
  }
  @Override public boolean onCommand(CommandSender sender,Command cmd,String label,String[] args) {
    if (!sender.hasPermission("enjaptoi.admin")) {sender.sendMessage("No permission");return true;}
    if (args.length==0){sender.sendMessage("/ejt pause | resume | status | reload | test <event>");return true;}
    try { switch(args[0].toLowerCase(Locale.ROOT)) {
      case "pause" -> {store.setPaused(true);sender.sendMessage("Paused");}
      case "resume" -> {store.setPaused(false);sender.sendMessage("Resumed (UNCERTAIN events remain held)");}
      case "reload" -> {reloadConfig();sender.sendMessage("Config reloaded (HTTP host/port require restart)");}
      case "status" -> sender.sendMessage("Pending="+store.count("PENDING")+", uncertain="+store.count("UNCERTAIN")+", paused="+store.paused()+", broadcaster="+getConfig().getString("broadcaster")+", receiver="+(managedReceiver!=null && managedReceiver.alive()));
      case "test" -> {if(args.length<2){sender.sendMessage("Specify event key");break;} Player p=Bukkit.getPlayerExact(getConfig().getString("broadcaster","Yirue"));if(p==null){sender.sendMessage("Broadcaster offline");break;} executeEvent(p,args[1]);}
      default -> sender.sendMessage("Unknown subcommand");
    } } catch(SQLException e) { storageFailed=true;sender.sendMessage("Event storage unavailable; restart and review state. Success cannot be confirmed."); }
    return true;
  }
  private boolean executeEvent(Player p,String event) {
    boolean success=true;
    switch(event) {
      case "buff" -> {PotionEffectType[] t={PotionEffectType.SPEED,PotionEffectType.STRENGTH,PotionEffectType.REGENERATION,PotionEffectType.RESISTANCE,PotionEffectType.JUMP_BOOST,PotionEffectType.HASTE};success=p.addPotionEffect(new PotionEffect(t[random.nextInt(t.length)],1200,0,true,true));}
      case "debuff" -> {PotionEffectType[] t={PotionEffectType.SLOWNESS,PotionEffectType.WEAKNESS,PotionEffectType.MINING_FATIGUE,PotionEffectType.BLINDNESS,PotionEffectType.HUNGER,PotionEffectType.NAUSEA};success=p.addPotionEffect(new PotionEffect(t[random.nextInt(t.length)],600,0,true,true));}
      case "bread" -> {Map<Integer,ItemStack> left=p.getInventory().addItem(new ItemStack(Material.BREAD,5));left.values().forEach(it->p.getWorld().dropItemNaturally(p.getLocation(),it));}
      case "pickaxe" -> {ItemStack item=new ItemStack(Material.DIAMOND_PICKAXE);Damageable meta=(Damageable)item.getItemMeta();meta.setDamage(item.getType().getMaxDurability()-1);item.setItemMeta(meta);Map<Integer,ItemStack> left=p.getInventory().addItem(item);left.values().forEach(it->p.getWorld().dropItemNaturally(p.getLocation(),it));}
      case "clear" -> {p.getInventory().clear();p.getInventory().setArmorContents(new ItemStack[4]);p.getInventory().setItemInOffHand(null);}
      case "chancekill" -> {success=random.nextInt(100)<15;if(success)p.setHealth(0.0);}
      case "kill" -> p.setHealth(0.0);
      case "mob" -> {EntityType[] types={EntityType.ZOMBIE,EntityType.SKELETON,EntityType.SPIDER,EntityType.CREEPER,EntityType.HUSK,EntityType.STRAY}; Location at=findSpawn(p);if(at==null)success=false;else p.getWorld().spawnEntity(at,types[random.nextInt(types.length)]);}
      case "move" -> {Location at=findTeleport(p,false);if(at==null)success=false;else success=p.teleport(at);}
      case "surface" -> {Location at=findTeleport(p,true);if(at==null)success=false;else success=p.teleport(at);}
      default -> {success=false;}
    }
    String msg="[엔잡퇴] "+event+(success?" 실행":" 실패/취소");p.sendMessage(msg);p.showTitle(net.kyori.adventure.title.Title.title(Component.text("엔잡퇴"),Component.text(msg)));
    p.playSound(p.getLocation(),Sound.BLOCK_NOTE_BLOCK_PLING,1f,1f);
    return success;
  }
  private Location findSpawn(Player p) {
    Location origin=p.getLocation(); int min=getConfig().getInt("spawn-min-radius",3),max=getConfig().getInt("spawn-max-radius",7);
    for(int i=0;i<10;i++){double a=random.nextDouble()*Math.PI*2;double r=min+random.nextDouble()*Math.max(1,max-min);Location at=origin.clone().add(Math.cos(a)*r,0,Math.sin(a)*r);Location safe=safeAt(at.getWorld(),at.getBlockX(),at.getBlockY(),at.getBlockZ());if(safe!=null)return safe;}return null;
  }
  private Location findTeleport(Player p,boolean surface) {
    return SafeTeleport.destination(p,surface,random);
  }
  private Location safeAt(World w,int x,int y,int z){
    if(y<=w.getMinHeight()||y+2>=w.getMaxHeight())return null;
    Block below=w.getBlockAt(x,y-1,z),feet=w.getBlockAt(x,y,z),head=w.getBlockAt(x,y+1,z);
    if(!below.getType().isSolid()||below.isLiquid()||feet.isLiquid()||head.isLiquid()||!feet.isPassable()||!head.isPassable())return null;
    if(below.getType().name().contains("MAGMA")||below.getType().name().contains("CACTUS"))return null;
    return new Location(w,x+0.5,y,z+0.5);
  }
}
