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
  Response post(HttpServer server,String body,String token) throws Exception {return post(server,body,token,null,null);}
  Response post(HttpServer server,String body,String token,String instance,String cheese) throws Exception {return post(server,body,token,instance,cheese,null);}
  Response post(HttpServer server,String body,String token,String instance,String cheese,String donor) throws Exception {
    HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:"+server.getAddress().getPort()+"/event").openConnection(Proxy.NO_PROXY);
    c.setConnectTimeout(2000);c.setReadTimeout(2000);c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("X-EJT-Token",token);
    if(instance!=null)c.setRequestProperty("X-EJT-Instance",instance);
    if(cheese!=null)c.setRequestProperty("X-EJT-Cheese",cheese);
    if(donor!=null)c.setRequestProperty("X-EJT-Donor",donor);
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
  @Test void staleReceiverCannotDeliverToRestartedServer() throws Exception {
    try(EventStore store=new EventStore(temp.resolve("events.sqlite3"))) {
      HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
      server.createContext("/event",new BridgeEndpoint("private-token","new-instance",store::enqueue));server.start();
      try {
        HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:"+server.getAddress().getPort()+"/event").openConnection(Proxy.NO_PROXY);
        c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("X-EJT-Token","private-token");c.setRequestProperty("X-EJT-Instance","old-instance");
        try {try(var out=c.getOutputStream()){out.write("stale-id\tbread".getBytes(StandardCharsets.UTF_8));}assertEquals(409,c.getResponseCode());}
        finally{c.disconnect();}
        assertEquals(0,store.count("PENDING"));
        assertEquals(new Response(200,"queued"),post(server,"manual-test\tbread","private-token"));
      } finally {server.stop(0);}
    }
  }

  @Test void verifiedGameAmountRequiresCurrentInstanceAndMatchingEffect() throws Exception {
    try(EventStore store=new EventStore(temp.resolve("amounts.db"))) {
      HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
      server.createContext("/event",BridgeEndpoint.managed("token","instance",store::enqueue));server.start();
      try {
        assertEquals(400,post(server,"bad1\tmove","token",null,"1000").status());
        assertEquals(400,post(server,"bad2\tmove","token","instance","5000").status());
        assertEquals(400,post(server,"bad3\tmove","token","instance","1000\"<tag>").status());
        assertEquals(200,post(server,"good\tmove","token","instance","1000").status());
        assertEquals("duplicate",post(server,"good\tmove","token","instance","1000").body());
        var e=store.begin();assertEquals(1000,e.cheese());store.complete(e.id());assertNull(store.begin());
        assertEquals(200,post(server,"manual\tbread","token").status());assertEquals(0,store.begin().cheese());
      } finally {server.stop(0);}
    }
  }

  String encoded(String name){return java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(name.getBytes(StandardCharsets.UTF_8));}
  @Test void nicknameTravelsWithDurableReceiptAndUnsafeHeadersBecomeAnonymous() throws Exception {
    try(EventStore store=new EventStore(temp.resolve("donor.db"))) {
      HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
      server.createContext("/event",BridgeEndpoint.managed("token","instance",store::enqueue));server.start();
      try {
        assertEquals(new Response(200,"queued"),post(server,"good\tmove","token","instance","1000",encoded("홍길동")));
        assertEquals(new Response(200,"duplicate"),post(server,"good\tmove","token","instance","1000",encoded("다른이름")));
        var event=store.begin();assertEquals("홍길동",event.donor());store.complete(event.id());
        int i=0;
        for(String unsafe:java.util.List.of("%%%", "_w", "A".repeat(173), encoded("§a관리자"),encoded("홍\r\nInjected"),encoded("<click:run_command:/op>"))){
          assertEquals(200,post(server,"bad"+(i++)+"\tmove","token","instance","1000",unsafe).status());
          event=store.begin();assertNull(event.donor());store.complete(event.id());
        }
        assertEquals(200,post(server,"legacy\tmove","token",null,null,encoded("홍길동")).status());
        event=store.begin();assertNull(event.donor());assertEquals(0,event.cheese());store.complete(event.id());
        assertNull(store.begin());
      }finally{server.stop(0);}
    }
  }

}
