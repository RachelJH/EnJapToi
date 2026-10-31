package kr.enjaptoi;
import java.io.File;
import java.nio.file.*;
import java.util.*;
/** Parent JVM intentionally halts, bypassing plugin cleanup. */
public class ManagedReceiverProbe {
  public static void main(String[] args)throws Exception {
    String code="import sys,os;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from bridge.lifecycle import ParentLifetime;import time;ParentLifetime(sys.stdin.buffer,terminate=lambda n:(Path(sys.argv[3]).write_text('stopped'),os._exit(n)));Path(sys.argv[2]).write_text(str(os.getpid()));time.sleep(60)";
    new ManagedReceiver(List.of(args[0],"-c",code,args[1],args[2],args[3]),Map.of(),new File(args[4]));
    long deadline=System.nanoTime()+5_000_000_000L;
    while(!Files.exists(Path.of(args[2])) && System.nanoTime()<deadline)Thread.sleep(20);
    if(!Files.exists(Path.of(args[2])))System.exit(2);
    Runtime.getRuntime().halt(0);
  }
}
