package kr.enjaptoi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;
class ManagedReceiverTest {
  @TempDir Path temp;
  String python(){return System.getenv().getOrDefault("ENJAPTOI_TEST_PYTHON",System.getProperty("os.name").startsWith("Windows")?"python":"python3");}
  @Test void normalCloseEndsChild()throws Exception {
    try(ManagedReceiver child=new ManagedReceiver(List.of(python(),"-c","import sys;sys.stdin.buffer.read()"),Map.of(),temp.resolve("child.log").toFile())){
      assertTrue(child.alive());child.close();assertFalse(child.alive());
    }
  }
  @Test void killedParentJvmStillClosesChildPipe()throws Exception {
    Path repo=Path.of(System.getProperty("user.dir")).getParent();
    String exe=Path.of(System.getProperty("java.home"),"bin",System.getProperty("os.name").startsWith("Windows")?"java.exe":"java").toString();
    String cp=System.getProperty("surefire.test.class.path",System.getProperty("java.class.path"));
    Path pid=temp.resolve("pid"),marker=temp.resolve("stopped");
    Process parent=new ProcessBuilder(exe,"-cp",cp,"kr.enjaptoi.ManagedReceiverProbe",python(),repo.toString(),pid.toString(),marker.toString(),temp.resolve("child.log").toString()).redirectErrorStream(true).redirectOutput(temp.resolve("parent.log").toFile()).start();
    try {
      assertTrue(parent.waitFor(8,TimeUnit.SECONDS));assertEquals(0,parent.exitValue());
      long deadline=System.nanoTime()+3_000_000_000L;
      while(!Files.exists(marker) && System.nanoTime()<deadline)Thread.sleep(20);
      assertTrue(Files.exists(marker),"Python lifetime watchdog must run even after JVM halt");
    } finally {if(parent.isAlive())parent.destroyForcibly();}
  }
}
