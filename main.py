import os
import requests
import socket
import struct
import subprocess
import sys
import uuid
import websocket

from dotenv import load_dotenv
from enum import IntEnum
from json import dumps, loads
from time import time

load_dotenv()

is_windows = sys.platform == "win32"


class Presence:
	# https://github.com/niveshbirangal/discord-rpc/blob/master/rpc.py
	HANDSHAKE = 0
	FRAME = 1
	CLOSE = 2

	def __init__(self, client_id):
		self.client_id = str(client_id)
		self._connect()
		self._handshake()

	def _connect(self):
		if is_windows:
			_pipe_pattern = r"\\?\pipe\discord-ipc-{}"
			for i in range(10):
				path = _pipe_pattern.format(i)
				try:
					self._f = open(path, "w+b")
				except OSError as e:
					print(f"Couldn't open {path}: {e}")
				else:
					break
			else:
				raise RuntimeError(
					"Failed to connect to Discord pipe (is Discord open?)"
				)
		else:
			self._sock = socket.socket(socket.AF_UNIX)
			for env_key in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
				if dir_path := os.environ.get(env_key):
					break
			else:
				dir_path = "/tmp"
			pipe_pattern = os.path.join(dir_path, "discord-ipc-{}")

			for i in range(10):
				path = pipe_pattern.format(i)
				if not os.path.exists(path):
					continue
				try:
					self._sock.connect(path)
				except OSError as e:
					print(f"Couldn't open {path}: {e}")
				else:
					break
			else:
				raise RuntimeError(
					"Failed to connect to Discord pipe (is Discord open?)"
				)

	def _handshake(self):
		self.send({"v": 1, "client_id": self.client_id}, self.HANDSHAKE)
		ret_op, ret_data = self.recv()
		if (
			ret_op == self.FRAME
			and ret_data["cmd"] == "DISPATCH"
			and ret_data["evt"] == "READY"
		):
			print("Connected to RPC")
			return
		else:
			if ret_op == self.CLOSE:
				self.close()
			raise RuntimeError(ret_data)

	def send(self, data, op):
		data_str = dumps(data, separators=(",", ":"))
		data_bytes = data_str.encode("utf-8")
		header = struct.pack("<II", op, len(data_bytes))
		if is_windows:
			self._f.write(header)
			self._f.flush()
			self._f.write(data_bytes)
			self._f.flush()
		else:
			self._sock.sendall(header)
			self._sock.sendall(data_bytes)

	def recv(self):
		header = self._recv_exactly(8)
		op, length = struct.unpack("<II", header)
		payload = self._recv_exactly(length)
		data = loads(payload.decode("utf-8"))
		return op, data

	def _recv_exactly(self, size):
		buf = b""
		remaining = size
		while remaining:
			if is_windows:
				chunk = self._f.read(size)
			else:
				chunk = self._sock.recv(size)
			buf += chunk
			remaining -= len(chunk)

		return buf

	def set_activity(self, act):
		self.send(
			{
				"cmd": "SET_ACTIVITY",
				"args": {"pid": os.getpid(), "activity": act},
				"nonce": str(uuid.uuid1()),
			},
			self.FRAME,
		)
		_op, data = self.recv()
		if "data" in data and "message" in data["data"]:
			print(data["data"]["message"])

	def close(self):
		try:
			self.send({}, self.CLOSE)
		finally:
			if is_windows:
				self._f.close()
			else:
				self._sock.close()


class Client:
	# https://github.com/Sheepposu/osu.py/
	def __init__(self, client_id, client_secret):
		self.client_id = client_id
		self.client_secret = client_secret
		self.refresh_token = None
		self.get_oauth_token()

	def get_oauth_token(self):
		resp = requests.post(
			"https://osu.ppy.sh/oauth/token/",
			data={
				"client_id": self.client_id,
				"client_secret": self.client_secret,
				"grant_type": "client_credentials",
				"scope": "public",
			},
		)
		resp.raise_for_status()
		resp = resp.json()
		if "refresh_token" in resp:
			self.refresh_token = resp["refresh_token"]
		self._token = resp["access_token"]
		self.expire_time = time() + resp["expires_in"] - 5

	def refresh_access_token(self):
		data = {
			"client_id": self.client_id,
			"client_secret": self.client_secret,
		}
		if self.refresh_token:
			data.update(
				{
					"grant_type": "refresh_token",
					"refresh_token": self.refresh_token,
				}
			)
		else:
			data.update({"grant_type": "client_credentials", "scope": "public"})
		resp = requests.post("https://osu.ppy.sh/oauth/token/", data=data)
		resp.raise_for_status()
		resp = resp.json()
		if "refresh_token" in resp:
			self.refresh_token = resp["refresh_token"]
		self._token = resp["access_token"]

	@property
	def token(self):
		if self.expire_time <= time():
			self.refresh_access_token()
		return self._token

	@property
	def headers(self):
		return {"Authorization": f"Bearer {self.token}"}

	def get_player(self, player):
		resp = requests.get(
			"https://osu.ppy.sh/api/v2/users/" + player, headers=self.headers
		)
		resp.raise_for_status()
		return resp.json()


class State(IntEnum):
	# https://vk.cc/aA7DJJ
	MAINMENU = 0  # menus
	EDITINGMAP = 1  # editing
	PLAYING = 2  # playing
	GAMESHUTDOWN = 3  # menus
	SONGSELECTEDIT = 4  # song select edit
	SONGSELECT = 5  # song select
	NOIDEA = 6
	RESULTSSCREEN = 7  # results
	GAMESTARTUP = 10  # menus
	MULTIROOMS = 11  # menus
	MULTIROOM = 12  # multi room
	MULTISONGSELECT = 13  # song select
	MULTIRESULTSSCREEN = 14  # results
	DIRECT = 15  # osu!direct
	RANKINGTAPCOOP = 17  # results
	RANKINGTEAM = 18  # results
	PROCESSINGBEATMAPS = 19  # menus
	TOURNEY = 22


class Activity:
	player_id = os.getenv("PLAYER_ID")
	client_id = os.getenv("CLIENT_ID")
	client_secret = os.getenv("CLIENT_SECRET")
	client = Client(client_id, client_secret)

	@classmethod
	def get_presence(cls, data):
		state = data["menu"]["state"]
		bm = data["menu"]["bm"]
		song = bm["metadata"]
		stats = bm["stats"]
		play = data["gameplay"]
		user_stats = cls.client.get_player(cls.player_id)

		act = {
			"buttons": [
				{
					"label": f"{user_stats['username']} #{user_stats['statistics']['global_rank']:,}",
					"url": f"https://osu.ppy.sh/users/{cls.player_id}",
				}
			],
			"assets": {
				"small_image": f"https://a.ppy.sh/{cls.player_id}?1604803914.jpeg",
				"small_text": f"Playing osu!{['', 'taiko', 'catch', 'mania'][data['menu']['gameMode']]}",
			},
		}

		if bm["set"] > 0:
			url = f"https://assets.ppy.sh/beatmaps/{bm['set']}/covers/list.jpg"
			resp = requests.get(url)
			if resp.status_code != 200:
				url = "https://github.com/ppy/osu/blob/master/assets/lazer-nuget.png?raw=true"
			act["assets"].update(
				{"large_image": url, "large_text": cls.song_name(song, True, False)}
			)
		else:
			act["assets"].update(
				{
					"large_image": "https://github.com/ppy/osu/blob/master/assets/lazer-nuget.png?raw=true",
					"large_text": cls.song_name(song, True, False),
				}
			)

		match state:
			case State.MAINMENU | State.GAMESHUTDOWN | State.GAMESTARTUP | State.PROCESSINGBEATMAPS | State.MULTIROOMS:
				act.update(
					{"details": "In menus", "state": cls.song_name(song, diff=False)}
				)

			case State.SONGSELECTEDIT:
				act.update(
					{
						"details": "Selecting a beatmap to edit",
						"state": cls.song_name(song),
					}
				)
				act["buttons"].append(
					{"label": cls.song_stats(stats), "url": cls.beatmap_link(data)}
				)

			case State.EDITINGMAP:  # editing
				act.update(
					{
						"details": "Editing a beatmap",
						"state": cls.song_name(song, diff=False),
					}
				)

			case State.SONGSELECT | State.MULTISONGSELECT:  # song select
				act.update(
					{
						"details": f"Selecting a beatmap (+{data['menu']['mods']['str']})",
						"state": cls.song_name(song),
					}
				)
				act["buttons"].append(
					{"label": cls.song_stats(stats), "url": cls.beatmap_link(data)}
				)

			case State.MULTIROOM:
				act.update({"details": "In a multi room", "state": cls.song_name(song)})

			case State.PLAYING:  # playing
				if play["name"] == user_stats["username"]:
					act.update(
						{
							"details": f"Playing a beatmap (+{data['menu']['mods']['str']})",
							"state": cls.song_name(song),
						}
					)
				else:
					act.update(
						{
							"details": f"Watching a replay by {play['name']} (+{data['menu']['mods']['str']})",
							"state": cls.song_name(song),
						}
					)
				act["buttons"].append(
					{
						"label": f"{play['hits']['grade']['current']} {play['accuracy']:.2f}% {play['combo']['current']}x {play['pp']['current']}pp {int(play['hits']['unstableRate'])}UR",
						"url": cls.beatmap_link(data),
					}
				)

			case State.RESULTSSCREEN | State.MULTIRESULTSSCREEN | State.RANKINGTAPCOOP | State.RANKINGTEAM:
				if play["name"] == user_stats["username"]:
					act.update(
						{
							"details": f"Finished beatmap (+{data['menu']['mods']['str']})",
							"state": cls.song_name(song),
						}
					)
				else:
					act.update(
						{
							"details": f"Finished watching a replay by {play['name']} (+{data['menu']['mods']['str']})",
							"state": cls.song_name(song),
						}
					)
				act["buttons"].append(
					{
						"label": f"{play['hits']['grade']['current']} {play['accuracy']:.2f}% {play['combo']['max']}x {play['pp']['current']}pp {int(play['hits']['unstableRate'])}UR",
						"url": cls.beatmap_link(data),
					}
				)

			case State.DIRECT:  # osu!direct
				act.update(
					{"details": "Browsing osu!direct", "state": cls.song_name(song)}
				)

			case _:
				print("Could not find state", state)
				act.update({"details": "???", "state": cls.song_name(song)})

		return act

	@classmethod
	def song_name(cls, song, mapper=False, diff=True):
		name = f"{song['artist']} - {song['title']}"
		if mapper:
			name += f" ({song['mapper']})"
		if diff:
			name += f" [{song['difficulty']}]"
		return name

	@classmethod
	def song_stats(cls, stats):
		return f"{stats['fullSR']}★ AR:{stats['AR']:.1f} CS:{stats['CS']:.1f} HP:{stats['HP']}"

	@classmethod
	def beatmap_link(cls, data):
		bm = data["menu"]["bm"]
		gm = ["osu", "taiko", "fruits", "mania"][data["menu"]["gameMode"]]
		url = f"https://osu.ppy.sh/beatmapsets/{bm['set']}#{gm}/{bm['id']}"
		resp = requests.get(url)
		if resp.status_code != 200:
			url = "https://osu.ppy.sh/beatmapsets"
		return url


def main():
	next_time = time()
	act = {}

	def on_message(_ws, message):
		nonlocal next_time
		if time() < next_time:
			return  # is there a better way to do this

		nonlocal act
		next_time = time() + 4  # updates every 4s due to ratelimits
		data = loads(message)

		new_act = Activity.get_presence(data)
		if new_act != act:
			presence.set_activity(new_act)
			act = new_act

	subprocess.Popen(os.getenv("OSU_PATH"))
	subprocess.Popen(os.getenv("GOSUMEMORY_PATH"))
	socket = websocket.WebSocketApp(
		"ws://localhost:24050/ws",
		on_message=on_message,
		on_error=lambda _ws, exception: print(type(exception).__name__, exception),
		on_open=lambda _: print("Websocket open"),
	)
	presence = Presence(927639447539957761)
	socket.run_forever()


if __name__ == "__main__":
	main()
