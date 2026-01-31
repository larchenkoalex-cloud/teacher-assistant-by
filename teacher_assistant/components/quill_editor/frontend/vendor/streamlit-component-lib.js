// Minimal, dependency-free Streamlit component runtime.
// Implements the same postMessage protocol that Streamlit expects:
// - Receives: { type: "streamlit:render", args, disabled, ... }
// - Sends:    { isStreamlitMessage: true, type: "streamlit:componentReady", apiVersion: 1 }
// - Sends:    { isStreamlitMessage: true, type: "streamlit:setComponentValue", value, dataType: "json" }
// - Sends:    { isStreamlitMessage: true, type: "streamlit:setFrameHeight", height }
//
// This avoids ESM imports (which previously caused 404s like ./vendor/StreamlitReact).

(function (root) {
	function EventBus() {
		this._listeners = {};
	}
	EventBus.prototype.addEventListener = function (type, cb) {
		this._listeners[type] = this._listeners[type] || [];
		this._listeners[type].push(cb);
	};
	EventBus.prototype.removeEventListener = function (type, cb) {
		if (!this._listeners[type]) return;
		this._listeners[type] = this._listeners[type].filter(function (f) {
			return f !== cb;
		});
	};
	EventBus.prototype.dispatchEvent = function (evt) {
		var list = this._listeners[evt.type] || [];
		for (var i = 0; i < list.length; i++) {
			try {
				list[i](evt);
			} catch (e) {
				console.error(e);
			}
		}
	};

	var MSG = {
		COMPONENT_READY: "streamlit:componentReady",
		SET_COMPONENT_VALUE: "streamlit:setComponentValue",
		SET_FRAME_HEIGHT: "streamlit:setFrameHeight",
	};

	var Streamlit = {
		API_VERSION: 1,
		RENDER_EVENT: "streamlit:render",
		events: new EventBus(),
		_registeredMessageListener: false,
		_lastFrameHeight: null,

		setComponentReady: function () {
			if (!Streamlit._registeredMessageListener) {
				window.addEventListener("message", Streamlit._onMessageEvent);
				Streamlit._registeredMessageListener = true;
			}
			Streamlit._sendBackMsg(MSG.COMPONENT_READY, { apiVersion: Streamlit.API_VERSION });
		},

		setFrameHeight: function (height) {
			if (height === undefined || height === null) {
				height = document.body ? document.body.scrollHeight : 0;
			}
			if (height !== Streamlit._lastFrameHeight) {
				Streamlit._lastFrameHeight = height;
				Streamlit._sendBackMsg(MSG.SET_FRAME_HEIGHT, { height: height });
			}
		},

		setComponentValue: function (value) {
			Streamlit._sendBackMsg(MSG.SET_COMPONENT_VALUE, { value: value, dataType: "json" });
		},

		_onMessageEvent: function (event) {
			try {
				var data = event.data;
				if (!data || !data.type) return;
				if (data.type === Streamlit.RENDER_EVENT) {
					Streamlit._onRenderMessage(data);
				}
			} catch (e) {
				console.error(e);
			}
		},

		_onRenderMessage: function (msg) {
			var args = msg.args;
			if (args == null) {
				console.error("Got null args in onRenderMessage. This should never happen");
				args = {};
			}
			var detail = { disabled: Boolean(msg.disabled), args: args };
			var evt = new CustomEvent(Streamlit.RENDER_EVENT, { detail: detail });
			Streamlit.events.dispatchEvent(evt);
		},

		_sendBackMsg: function (type, payload) {
			var msg = {};
			for (var k in payload) msg[k] = payload[k];
			msg.isStreamlitMessage = true;
			msg.type = type;
			window.parent.postMessage(msg, "*");
		},
	};

	root.Streamlit = Streamlit;
	root.streamlitComponentLib = { Streamlit: Streamlit };
})(typeof window !== "undefined" ? window : this);
