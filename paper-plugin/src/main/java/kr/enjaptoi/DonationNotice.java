package kr.enjaptoi;
import net.kyori.adventure.text.Component;
final class DonationNotice {
  static int amount(String effect) {
    return switch(effect){case "buff","move","bread","pickaxe"->1000;case "mob","debuff"->2000;case "clear","chancekill","surface"->5000;case "kill"->30000;default->0;};
  }
  static void complete(EventStore store,EventStore.Event event,boolean applied,java.util.function.Consumer<Component> announce) throws java.sql.SQLException {
    store.complete(event.id()); // No public notice until DONE is durable; no replay after restart.
    if(applied){Component notice=message(event.effect(),event.cheese(),event.donor());if(notice!=null)announce.accept(notice);}
  }
  static String safeDonor(String value) {
    if(value==null)return null;
    value=value.replaceAll("^ +| +$", "");
    String folded=value.toLowerCase(java.util.Locale.ROOT);
    if(value.isEmpty() || value.codePointCount(0,value.length())>32 || value.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>128
        || java.util.Set.of("익명","익명의 후원자","anonymous").contains(folded))return null;
    if(!Character.isLetterOrDigit(value.codePointAt(0)))return null;
    if(!value.codePoints().allMatch(c->Character.isLetterOrDigit(c) || Character.getType(c)==Character.NON_SPACING_MARK
        || Character.getType(c)==Character.COMBINING_SPACING_MARK || Character.getType(c)==Character.ENCLOSING_MARK || " _-.".indexOf(c)>=0))return null;
    return value;
  }
  static Component message(String effect,int cheese) {return message(effect,cheese,null);}
  static Component message(String effect,int cheese,String donor) {
    if(cheese==0 || cheese!=amount(effect))return null;
    String label=switch(effect){case "buff"->"버프 효과";case "move"->"후렴과 효과";case "bread"->"밥 효과";case "pickaxe"->"다곡 효과";case "mob"->"몹 효과";case "debuff"->"디버프 효과";case "clear"->"삭제 효과";case "chancekill"->"랜덤 즉사 효과";case "surface"->"지상이동";case "kill"->"즉사 효과";default->"";};
    String name=safeDonor(donor);
    return Component.text("\""+(name==null?"익명의 후원자":name)+"\"님이 \""+String.format(java.util.Locale.ROOT,"%,d",cheese)+"치즈\"를 후원하셨습니다! ("+label+")");
  }
}
