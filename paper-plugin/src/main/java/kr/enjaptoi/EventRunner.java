package kr.enjaptoi;

import java.sql.SQLException;
import java.util.function.Consumer;
import java.util.function.Function;
import net.kyori.adventure.text.Component;
import org.bukkit.entity.Player;

/** Main-thread queue boundary: a dead/offline target never acquires an event. */
final class EventRunner {
  private long lastExecution;
  boolean run(EventStore store,Player player,long now,long intervalMillis,
      Function<EventStore.Event,Boolean> execute,Consumer<Component> announce)throws SQLException {
    if(!EffectActions.ready(player) || now-lastExecution<intervalMillis)return false;
    EventStore.Event event=store.begin();
    if(event==null)return false;
    lastExecution=now;
    boolean applied;
    try {applied=!event.effect().equals("mob") && execute.apply(event);}
    catch(RuntimeException e){store.uncertain(event.id());throw e;}
    DonationNotice.complete(store,event,applied,announce);
    return true;
  }
}
