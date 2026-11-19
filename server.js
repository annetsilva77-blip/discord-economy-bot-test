
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");

const app = express();
const server = http.createServer(app);

const io = new Server(server, {
  cors: { origin: "*" }
});

const players = new Map();

app.get("/", (req, res) => {
  res.send("StreetWorld multiplayer server is running!");
});

io.on("connection", socket => {
  socket.on("joinWorld", data => {
    const player = {
      id: socket.id,
      name: String(data?.name || "Driver").slice(0, 16),
      x: 0,
      z: 0,
      rot: 0,
      color: Math.floor(Math.random() * 0xffffff)
    };

    players.set(socket.id, player);

    socket.emit(
      "players",
      [...players.values()].filter(p => p.id !== socket.id)
    );

    socket.broadcast.emit("playerJoined", player);
  });

  socket.on("move", data => {
    const player = players.get(socket.id);
    if (!player || !data) return;

    const x = Number(data.x);
    const z = Number(data.z);
    const rot = Number(data.rot);

    if (![x, z, rot].every(Number.isFinite)) return;

    player.x = x;
    player.z = z;
    player.rot = rot;

    socket.broadcast.emit("playerMoved", player);
  });

  socket.on("disconnect", () => {
    players.delete(socket.id);
    socket.broadcast.emit("playerLeft", socket.id);
  });
});

const PORT = process.env.PORT || 3000;

server.listen(PORT, "0.0.0.0", () => {
  console.log("StreetWorld server running on port " + PORT);
});
