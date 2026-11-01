package kr.enjaptoi;
import net.kyori.adventure.text.Component;
final class DonationNotice {
  static int amount(String effect) {
    return switch(effect){case "buff","move","bread","pickaxe"->1000;case "mob","debuff"->2000;case "clear","chancekill","surface"->5000;case "kill"->30000;default->0;};
  }
  static void complete(EventStore store,EventStore.Event event,boolean applied,java.util.function.Consumer<Component> announce) throws java.sql.SQLException {
    store.complete(event.id()); // No public notice until DONE is durable; no replay after restart.
    if(applied){Component notice=message(event.effect(),event.cheese());if(notice!=null)announce.accept(notice);}
  }
  static Component message(String effect,int cheese) {
    if(cheese==0 || cheese!=amount(effect))return null;
    String label=switch(effect){case "buff"->"버프 효과";case "move"->"후렴과 효과";case "bread"->"밥 효과";case "pickaxe"->"다곡 효과";case "mob"->"몹 효과";case "debuff"->"디버프 효과";case "clear"->"삭제 효과";case "chancekill"->"랜덤 즉사 효과";case "surface"->"지상이동 효과";case "kill"->"즉사 효과";default->"";};
    return Component.text("\"익명의 후원자\"님이 \""+String.format(java.util.Locale.ROOT,"%,d",cheese)+"치즈\"를 후원하셨습니다! ("+label+")");
  }
}
