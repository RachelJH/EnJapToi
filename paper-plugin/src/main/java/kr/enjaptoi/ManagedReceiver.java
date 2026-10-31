package kr.enjaptoi;

import java.io.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Parent owns child's stdin pipe. OS closes it even when the JVM is killed. */
final class ManagedReceiver implements AutoCloseable {
  private final Process child;
  ManagedReceiver(List<String> command,Map<String,String> environment,File log) throws IOException {
    ProcessBuilder builder=new ProcessBuilder(command);
    builder.environment().putAll(environment);
    builder.redirectErrorStream(true);
    builder.redirectOutput(ProcessBuilder.Redirect.appendTo(log));
    child=builder.start(); // stdin remains PIPE and is never inherited or detached.
  }
  boolean alive(){return child.isAlive();}
  @Override public void close() {
    try{child.getOutputStream().close();}catch(IOException ignored){}
    try {
      if(!child.waitFor(3,TimeUnit.SECONDS)) {
        child.destroy();
        if(!child.waitFor(1,TimeUnit.SECONDS))child.destroyForcibly();
      }
    } catch(InterruptedException e){child.destroyForcibly();Thread.currentThread().interrupt();}
  }
}
