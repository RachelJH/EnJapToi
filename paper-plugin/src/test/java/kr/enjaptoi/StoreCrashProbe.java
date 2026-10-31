package kr.enjaptoi;
import java.nio.file.Path;
/** Test subprocess deliberately exits without close/shutdown hooks. */
public class StoreCrashProbe {
  public static void main(String[] args) throws Exception {
    EventStore store=new EventStore(Path.of(args[0]));
    store.enqueue("crash-id","bread");
    if(args[1].equals("intent"))store.begin();
    Runtime.getRuntime().halt(0);
  }
}
