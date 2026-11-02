package kr.enjaptoi;

import com.sun.net.httpserver.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** No ACK escapes until the durable receiver returns successfully. */
final class BridgeEndpoint implements HttpHandler {
  @FunctionalInterface interface Receiver {
    EventStore.Receipt enqueue(String id,String effect) throws Exception;
  }
  @FunctionalInterface interface DonationReceiver {EventStore.Receipt enqueue(String id,String effect,int cheese,String donor)throws Exception;}
  private final byte[] token;
  private final DonationReceiver receiver;
  private final String instance;
  BridgeEndpoint(String token,Receiver receiver){this(token,null,receiver);}
  BridgeEndpoint(String token,String instance,Receiver receiver){this(token,instance,(id,effect,cheese,donor)->receiver.enqueue(id,effect),true);}
  private BridgeEndpoint(String token,String instance,DonationReceiver receiver,boolean marker){this.token=token.getBytes(StandardCharsets.UTF_8);this.instance=instance;this.receiver=receiver;}
  static BridgeEndpoint managed(String token,String instance,DonationReceiver receiver){return new BridgeEndpoint(token,instance,receiver,true);}
  @Override public void handle(HttpExchange exchange) throws IOException {
    try(exchange) {
      if(!"/event".equals(exchange.getRequestURI().getPath())){respond(exchange,404,"not found");return;}
      if(!"POST".equals(exchange.getRequestMethod())){respond(exchange,405,"method not allowed");return;}
      String supplied=exchange.getRequestHeaders().getFirst("X-EJT-Token");
      if(supplied==null || !MessageDigest.isEqual(token,supplied.getBytes(StandardCharsets.UTF_8))){respond(exchange,401,"unauthorized");return;}
      String sentInstance=exchange.getRequestHeaders().getFirst("X-EJT-Instance");
      if(sentInstance!=null && (instance==null || !MessageDigest.isEqual(instance.getBytes(StandardCharsets.UTF_8),sentInstance.getBytes(StandardCharsets.UTF_8)))){
        respond(exchange,409,"server_changed");return;
      }
      byte[] bytes=exchange.getRequestBody().readNBytes(4097);
      if(bytes.length>4096){respond(exchange,400,"invalid event");return;}
      String[] parts=new String(bytes,StandardCharsets.UTF_8).trim().split("\\t",-1);
      if(parts.length!=2 || !parts[0].matches("[A-Za-z0-9_-]{1,100}") || !parts[1].matches("buff|move|bread|pickaxe|debuff|clear|chancekill|surface|kill")){
        respond(exchange,400,"invalid event");return;
      }
      int cheese=0;
      String amount=exchange.getRequestHeaders().getFirst("X-EJT-Cheese");
      if(amount!=null){
        if(sentInstance==null || !amount.matches("1000|2000|3000|4000|5000|30000") || Integer.parseInt(amount)!=DonationNotice.amount(parts[1])){respond(exchange,400,"invalid cheese");return;}
        cheese=Integer.parseInt(amount);
      }
      String donor=null;
      String encodedDonor=exchange.getRequestHeaders().getFirst("X-EJT-Donor");
      if(encodedDonor!=null && cheese!=0 && sentInstance!=null && encodedDonor.matches("[A-Za-z0-9_-]{1,172}")){
        try {
          byte[] decoded=java.util.Base64.getUrlDecoder().decode(encodedDonor);
          String candidate=StandardCharsets.UTF_8.newDecoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
              .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(decoded)).toString();
          donor=DonationNotice.safeDonor(candidate);
        }catch(IllegalArgumentException | java.nio.charset.CharacterCodingException ignored){ /* Anonymous; never echo the input. */ }
      }
      EventStore.Receipt result;
      try { result=receiver.enqueue(parts[0],parts[1],cheese,donor); }
      catch(Exception e) {
        if(e instanceof InterruptedException)Thread.currentThread().interrupt();
        respond(exchange,503,"unavailable");return;
      }
      respond(exchange,result==EventStore.Receipt.CONFLICT?409:200,result.name().toLowerCase(java.util.Locale.ROOT));
    }
  }
  private static void respond(HttpExchange e,int status,String message) throws IOException {
    byte[] bytes=message.getBytes(StandardCharsets.UTF_8);e.sendResponseHeaders(status,bytes.length);
    try(var out=e.getResponseBody()){out.write(bytes);}
  }
}
