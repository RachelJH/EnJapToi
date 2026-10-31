// Local-only mock of REST + official Socket.IO 2.0.3 wire generation.
const http = require('http');
const url = require('url');
const ioFactory = require('socket.io');
const assert = require('assert');
const sockets = new Map();
let sessions = 0;
const server = http.createServer((req, res) => {
  const u = url.parse(req.url, true);
  res.setHeader('Content-Type', 'application/json');
  if (req.headers.authorization !== 'Bearer test-access') {
    res.writeHead(401); return res.end(JSON.stringify({code:401}));
  }
  if (u.pathname === '/open/v1/users/me') {
    return res.end(JSON.stringify({code:200,content:{channelId:'test-channel'}}));
  }
  if (u.pathname === '/open/v1/sessions/auth') {
    sessions++;
    return res.end(JSON.stringify({code:200,content:{url:`https://127.0.0.1?auth=test-${sessions}`}}));
  }
  if (u.pathname === '/open/v1/sessions/events/subscribe/donation') {
    assert.equal(req.method, 'POST');
    const socket = sockets.get(u.query.sessionKey);
    if (!socket) {res.writeHead(400); return res.end('{}');}
    socket.emit('SYSTEM', JSON.stringify({type:'subscribed',data:{eventType:'DONATION',channelId:'test-channel'}}));
    // Same content on a second connection is intentionally a SECOND receipt:
    // upstream has no unique donation ID, so we must not invent deduplication.
    socket.emit('DONATION', JSON.stringify({donationType:'CHAT',channelId:'test-channel',
      donatorChannelId:'private-donor',donatorNickname:'private-name',
      payAmount:'1000',donationText:'!밥 private-text'}));
    res.end(JSON.stringify({code:200,content:null}));
    if (sessions === 1) setTimeout(() => socket.disconnect(true), 250);
    return;
  }
  res.writeHead(404);res.end('{}');
});
const io = ioFactory(server, {transports:['websocket'], serveClient:false});
io.on('connection', socket => {
  assert.equal(socket.conn.transport.name, 'websocket');
  assert.ok(socket.handshake.query.EIO === '3');
  const key = 'test-key-' + sessions;
  sockets.set(key, socket);
  socket.on('disconnect', () => sockets.delete(key));
  socket.emit('SYSTEM', JSON.stringify({type:'connected',data:{sessionKey:key}}));
});
server.listen(0, '127.0.0.1', () => console.log(server.address().port));
