package kr.enjaptoi;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

class BridgeEndpointTest {
  @TempDir Path temp;
  record Response(int status,String body){}
  Response post(HttpServer server,String body,String token) throws Exception {
    HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:"+server.getAddress().getPort()+"/event").openConnection(Proxy.NO_PROXY);
    c.setConnectTimeout(2000);c.setReadTimeout(2000);c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("X-EJT-Token",token);
    try {try(var out=c.getOutputStream()){out.write(body.getBytes(StandardCharsets.UTF_8));}
      int status=c.getResponseCode();try(var in=status>=400?c.getErrorStream():c.getInputStream()){return new Response(status,new String(in.readAllBytes(),StandardCharsets.UTF_8));}
    } finally {c.disconnect();}
  }
  @Test void storageFailureReturns503AndSameIdCanRetryAfterRestart() throws Exception {
    AtomicBoolean fail=new AtomicBoolean();Path path=temp.resolve("events.sqlite3");
    AtomicReference<EventStore> store=new AtomicReference<>(new EventStore(path,c->{if(fail.get())throw new SQLException("disk unavailable");c.commit();}));
    HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
    server.createContext("/event",new BridgeEndpoint("private-token",(id,effect)->store.get().enqueue(id,effect)));server.start();
    try {
      fail.set(true);assertEquals(new Response(503,"unavailable"),post(server,"same-id\tbread","private-token"));
      assertEquals(503,post(server,"same-id\tbread","private-token").status());
      store.get().close();store.set(new EventStore(path));
      assertEquals(new Response(200,"queued"),post(server,"same-id\tbread","private-token"));
      assertEquals(new Response(200,"duplicate"),post(server,"same-id\tbread","private-token"));
      assertEquals(new Response(409,"conflict"),post(server,"same-id\tkill","private-token"));
      assertEquals(1,store.get().count("PENDING"));
    } finally {server.stop(0);store.get().close();}
  }
  @Test void receiptLostAfterCommitStillRetriesAsDuplicate() throws Exception {
    try(EventStore store=new EventStore(temp.resolve("events.sqlite3"))) {
      AtomicBoolean lose=new AtomicBoolean(true);
      HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
      server.createContext("/event",new BridgeEndpoint("private-token",(id,effect)->{
        EventStore.Receipt result=store.enqueue(id,effect);
        if(lose.getAndSet(false))throw new java.io.IOException("lost acknowledgement");return result;
      }));server.start();
      try {
        assertEquals(401,post(server,"id\tbread","wrong-token").status());
        assertEquals(400,post(server,"invalid","private-token").status());
        assertEquals(503,post(server,"id\tbread","private-token").status());
        assertEquals(new Response(200,"duplicate"),post(server,"id\tbread","private-token"));
        assertEquals(1,store.count("PENDING"));
      } finally {server.stop(0);}
    }
  }
}
