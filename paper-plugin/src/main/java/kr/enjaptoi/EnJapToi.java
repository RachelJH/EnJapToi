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
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.scheduler.BukkitTask;
import net.kyori.adventure.text.Component;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.*;

public class EnJapToi extends JavaPlugin implements CommandExecutor {
  private final Deque<String> queue = new ArrayDeque<>();
  private final Set<String> received = new HashSet<>();
  private final Random random = new SecureRandom();
  private boolean paused = false;
  private HttpServer server;
  private BukkitTask ticker;
  private File stateFile;
  private String token;
  private long lastExecution = 0;

  @Override public void onEnable() {
    saveDefaultConfig(); stateFile = new File(getDataFolder(), "state.yml"); loadState();
    try {
      File tokenFile = new File(getDataFolder(), "bridge-token.txt");
      if (!tokenFile.exists()) {
        byte[] bytes = new byte[32]; new SecureRandom().nextBytes(bytes);
        Files.writeString(tokenFile.toPath(), Base64.getUrlEncoder().withoutPadding().encodeToString(bytes), StandardCharsets.UTF_8);
      }
      token = Files.readString(tokenFile.toPath(), StandardCharsets.UTF_8).trim();
      server = HttpServer.create(new InetSocketAddress(getConfig().getString("listen-host", "127.0.0.1"), getConfig().getInt("listen-port",18765)), 0);
      server.createContext("/event", exchange -> {
        if (!"POST".equals(exchange.getRequestMethod())) { respond(exchange,405,"method not allowed"); return; }
        if (!token.equals(exchange.getRequestHeaders().getFirst("X-EJT-Token"))) { respond(exchange,401,"unauthorized"); return; }
        String body = new String(exchange.getRequestBody().readNBytes(4096), StandardCharsets.UTF_8).trim();
        // Simple wire format: unique ID TAB event key. Reject invalid data.
        String[] parts = body.split("\\t", -1);
        if (parts.length != 2 || !parts[0].matches("[A-Za-z0-9_-]{1,100}") || !parts[1].matches("buff|move|bread|pickaxe|mob|debuff|clear|chancekill|surface|kill")) {
          respond(exchange,400,"invalid event"); return;
        }
        try {
          String result = Bukkit.getScheduler().callSyncMethod(this, () -> {
            if (received.contains(parts[0])) return "duplicate";
            received.add(parts[0]); queue.addLast(parts[1]); saveState(); return "queued";
          }).get(5, TimeUnit.SECONDS);
          respond(exchange,200,result);
        } catch (Exception e) { respond(exchange,503,"unavailable"); }
      });
      server.start();
    } catch(Exception e) { getLogger().severe("Local HTTP bridge failed: " + e.getMessage()); getServer().getPluginManager().disablePlugin(this); return; }
    Objects.requireNonNull(getCommand("ejt")).setExecutor(this);
    ticker = Bukkit.getScheduler().runTaskTimer(this, () -> {
      if (paused || queue.isEmpty()) return;
      Player player = Bukkit.getPlayerExact(getConfig().getString("broadcaster", "Yirue"));
      if (player == null) return;
      long now = System.currentTimeMillis();
      if (now - lastExecution < getConfig().getLong("interval-ticks",60)*50) return;
      String event = queue.removeFirst(); saveState(); lastExecution=now;
      executeEvent(player,event);
    },20L,20L);
  }
  private static void respond(com.sun.net.httpserver.HttpExchange e,int status,String msg) throws IOException {
    byte[] bytes=msg.getBytes(StandardCharsets.UTF_8); e.sendResponseHeaders(status,bytes.length);
    try(OutputStream out=e.getResponseBody()){out.write(bytes);} }
  private void loadState() {
    if (!stateFile.exists()) return;
    FileConfiguration y=YamlConfiguration.loadConfiguration(stateFile);
    queue.addAll(y.getStringList("pending")); received.addAll(y.getStringList("received")); paused=y.getBoolean("paused",false);
  }
  private void saveState() {
    YamlConfiguration y=new YamlConfiguration(); y.set("pending",new ArrayList<>(queue)); y.set("received",new ArrayList<>(received)); y.set("paused",paused);
    try { y.save(stateFile); } catch(IOException e){getLogger().severe("Failed to save state: "+e.getMessage());}
  }
  @Override public void onDisable() {if(ticker!=null)ticker.cancel(); if(server!=null)server.stop(1); saveState();}
  @Override public boolean onCommand(CommandSender sender,Command cmd,String label,String[] args) {
    if (!sender.hasPermission("enjaptoi.admin")) {sender.sendMessage("No permission");return true;}
    if (args.length==0){sender.sendMessage("/ejt pause | resume | status | reload | test <event>");return true;}
    switch(args[0].toLowerCase(Locale.ROOT)) {
      case "pause" -> {paused=true;saveState();sender.sendMessage("Paused");}
      case "resume" -> {paused=false;saveState();sender.sendMessage("Resumed");}
      case "reload" -> {reloadConfig();sender.sendMessage("Config reloaded (HTTP host/port require restart)");}
      case "status" -> sender.sendMessage("Pending="+queue.size()+", paused="+paused+", broadcaster="+getConfig().getString("broadcaster"));
      case "test" -> {if(args.length<2){sender.sendMessage("Specify event key");break;} Player p=Bukkit.getPlayerExact(getConfig().getString("broadcaster","Yirue"));if(p==null){sender.sendMessage("Broadcaster offline");break;} executeEvent(p,args[1]);}
      default -> sender.sendMessage("Unknown subcommand");
    } return true;
  }
  private void executeEvent(Player p,String event) {
    boolean success=true;
    switch(event) {
      case "buff" -> {PotionEffectType[] t={PotionEffectType.SPEED,PotionEffectType.STRENGTH,PotionEffectType.REGENERATION,PotionEffectType.RESISTANCE,PotionEffectType.JUMP_BOOST,PotionEffectType.HASTE};p.addPotionEffect(new PotionEffect(t[random.nextInt(t.length)],1200,0,true,true));}
      case "debuff" -> {PotionEffectType[] t={PotionEffectType.SLOWNESS,PotionEffectType.WEAKNESS,PotionEffectType.MINING_FATIGUE,PotionEffectType.BLINDNESS,PotionEffectType.HUNGER,PotionEffectType.NAUSEA};p.addPotionEffect(new PotionEffect(t[random.nextInt(t.length)],600,0,true,true));}
      case "bread" -> {Map<Integer,ItemStack> left=p.getInventory().addItem(new ItemStack(Material.BREAD,5));left.values().forEach(it->p.getWorld().dropItemNaturally(p.getLocation(),it));}
      case "pickaxe" -> {ItemStack item=new ItemStack(Material.DIAMOND_PICKAXE);Damageable meta=(Damageable)item.getItemMeta();meta.setDamage(item.getType().getMaxDurability()-1);item.setItemMeta(meta);Map<Integer,ItemStack> left=p.getInventory().addItem(item);left.values().forEach(it->p.getWorld().dropItemNaturally(p.getLocation(),it));}
      case "clear" -> {p.getInventory().clear();p.getInventory().setArmorContents(new ItemStack[4]);p.getInventory().setItemInOffHand(null);}
      case "chancekill" -> {if(random.nextInt(100)<15)p.setHealth(0.0);}
      case "kill" -> p.setHealth(0.0);
      case "mob" -> {EntityType[] types={EntityType.ZOMBIE,EntityType.SKELETON,EntityType.SPIDER,EntityType.CREEPER,EntityType.HUSK,EntityType.STRAY}; Location at=findSpawn(p);if(at==null)success=false;else p.getWorld().spawnEntity(at,types[random.nextInt(types.length)]);}
      case "move" -> {Location at=findTeleport(p,false);if(at==null)success=false;else p.teleport(at);}
      case "surface" -> {Location at=findTeleport(p,true);if(at==null)success=false;else p.teleport(at);}
      default -> {success=false;}
    }
    String msg="[엔잡퇴] "+event+(success?" 실행":" 실패/취소");p.sendMessage(msg);p.showTitle(net.kyori.adventure.title.Title.title(Component.text("엔잡퇴"),Component.text(msg)));
    p.playSound(p.getLocation(),Sound.BLOCK_NOTE_BLOCK_PLING,1f,1f);
  }
  private Location findSpawn(Player p) {
    Location origin=p.getLocation(); int min=getConfig().getInt("spawn-min-radius",3),max=getConfig().getInt("spawn-max-radius",7);
    for(int i=0;i<10;i++){double a=random.nextDouble()*Math.PI*2;double r=min+random.nextDouble()*Math.max(1,max-min);Location at=origin.clone().add(Math.cos(a)*r,0,Math.sin(a)*r);Location safe=safeAt(at.getWorld(),at.getBlockX(),at.getBlockY(),at.getBlockZ());if(safe!=null)return safe;}return null;
  }
  private Location findTeleport(Player p,boolean surface) {
    World w=p.getWorld(); Location loc=p.getLocation();
    for(int i=0;i<10;i++){
      int x=loc.getBlockX(),z=loc.getBlockZ();
      if(!surface){double angle=random.nextDouble()*Math.PI*2;double r=Math.sqrt(random.nextDouble())*getConfig().getInt("random-teleport-radius",300);x+=(int)Math.round(Math.cos(angle)*r);z+=(int)Math.round(Math.sin(angle)*r);}
      // Scan down from current height for move, from max height for surface. Avoid cross-dimension teleports.
      int top=surface?w.getMaxHeight()-3:Math.min(w.getMaxHeight()-3,loc.getBlockY()+16);
      int bottom=surface?w.getMinHeight()+1:Math.max(w.getMinHeight()+1,loc.getBlockY()-32);
      for(int y=top;y>=bottom;y--){Location safe=safeAt(w,x,y,z);if(safe!=null)return safe;}
    }return null;
  }
  private Location safeAt(World w,int x,int y,int z){
    if(y<=w.getMinHeight()||y+2>=w.getMaxHeight())return null;
    Block below=w.getBlockAt(x,y-1,z),feet=w.getBlockAt(x,y,z),head=w.getBlockAt(x,y+1,z);
    if(!below.getType().isSolid()||below.isLiquid()||feet.isLiquid()||head.isLiquid()||!feet.isPassable()||!head.isPassable())return null;
    if(below.getType().name().contains("MAGMA")||below.getType().name().contains("CACTUS"))return null;
    return new Location(w,x+0.5,y,z+0.5);
  }
}
