import sys
from os import path
import sublime
import sublime_plugin
from pprint import pprint
import threading
import websocket
import json
import newterm
try:
	import thread
except ImportError:
	import _thread as thread
from time import sleep

show_connecting_message=True
lock=threading.Lock()
ws=None

def getSelections(view):
	selectionIndices = [(s.begin(), s.end()) for s in view.sel()]
	selections = [
					{
						"start": {
							"line": srow,
							"character": scol
						},
						"end": {
							"line": erow,
							"character": ecol
						}
					} for ((srow, scol), (erow, ecol)) in [(view.rowcol(s), view.rowcol(e)) for (s, e) in selectionIndices] ]
	return selectionIndices, selections


def sync_active_file():
	global ws
	view = sublime.active_window().active_view()
	selectionIndices, selections = getSelections(view)
	if (ws is not None):
		ws.send(json.dumps({
			"type": "ACTIVE_FILE",
			"payload": {
				"uri": {
					"fsPath": view.file_name()
				},
				"language": view.scope_name(0).split(" ")[0][7:], # remove "source." from the string
				"contents": view.substr(sublime.Region(0, view.size())),
				"selections": selections,
				"selectionIndices": selectionIndices,
				"visibleRanges": [] # TODO: implement
			}
		}))

def disconnect():
	global ws
	if (ws is not None):
		ws.on_error = None
		ws.on_message = None
		ws.on_open = None
		ws.close()
		ws.close = None
		print("Deleting ws")
		del ws
	ws = None

def on_message(ws, message):
	data = json.loads(message)
	window = sublime.active_window()
	view = window.active_view()
	# TODO: implement a router
	_type = data.get("type")
	payload = data.get("payload")
	if (_type == "SCROLL_TO"):
		region=sublime.Region(payload.get("start"), payload.get("end"))
		view.sel().clear()
		view.sel().add(region)
		view.show_at_center(region)
	elif (_type == "EDIT_DOCUMENT"):
		edits=payload.get("edits")
		view.run_command("windsor_edit_document", {"edits": edits})
	elif (_type == "EXECUTE"):
		command=payload.get("shellPath") + " " + " ".join(payload.get("shellArgs"))
		# TODO: @trello https://trello.com/c/ksbI6OCt figure out how to inject the terminal with the command
		newterm.launch_terminal(path.dirname(view.file_name()))

def on_error(ws, error):
	print(error)
	disconnect()
	sleep(5)
	connect()

def on_close(ws):
	print("### closed ###")

def on_open(ws):
	global show_connecting_message
	print("Connected")
	sublime.active_window().status_message("Connected to Windsor")
	show_connecting_message=True
	sync_active_file()

def connect():
	global ws, show_connecting_message
	print("Connecting")
	if(show_connecting_message):
		sublime.active_window().status_message("Trying to connect to Windsor")
		show_connecting_message=False
	lock.acquire()
	if (ws is None):
		websocket.enableTrace(True)
		ws = websocket.WebSocketApp("ws://localhost:61952/",
			on_message = on_message,
			on_error = on_error,
			on_close = on_close)
		ws.on_open = on_open
		wst = threading.Thread(target=ws.run_forever)
		wst.start()
	lock.release()

def plugin_loaded():
	connect()

def plugin_unloaded():
	disconnect()

class WindsorEditDocumentCommand(sublime_plugin.TextCommand):
	def run(self, group, edits=[]):
		for edit in edits:
			region=sublime.Region(edit.get("start"), edit.get("end"))
			self.view.replace(group, region, edit.get("text"))
	def is_visible():
		return False

class Windsor(sublime_plugin.EventListener):
	def on_modified_async(self, view):
		global ws;
		if (ws is not None and ws.sock.connected and view == sublime.active_window().active_view()):
			ws.send(json.dumps({
				"type": "ACTIVE_FILE_UPDATE",
				"payload": {
					"uri": {
						"fsPath": view.file_name()
					},
					"language": view.scope_name(0).split(" ")[0][7:], # remove "source." from the string
					"contents": view.substr(sublime.Region(0, view.size())),
				}
			}));
	
	def on_post_save_async(self, view):
		global ws
		if (ws is not None and ws.sock.connected and view == sublime.active_window().active_view()):
			ws.send(json.dumps({
				"type": "ACTIVE_FILE_SAVE",
				"payload": {
					"uri": {
						"fsPath": view.file_name()
					},
					"language": view.scope_name(0).split(" ")[0][7:], # remove "source." from the string
					"contents": view.substr(sublime.Region(0, view.size())),
				}
			}))
	def on_activated_async(self, view):
		global ws
		sync_active_file()
	def on_selection_modified_async(self, view):
		global ws
		if (ws is not None and ws.sock.connected and view == sublime.active_window().active_view()):
			selectionIndices, selections = getSelections(view)
			ws.send(json.dumps({
				"type": "ACTIVE_FILE_SELECTIONS",
				"payload": {
					"selections": selections,
					"selectionIndices": selectionIndices
				}
			}))
