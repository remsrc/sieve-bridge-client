/*
 * Native Messaging transport client for Sieve Reloaded.
 * License: AGPL-3.0-or-later
 */

/* global browser */

const HOST_NAME = "de.remsrc.sieve_bridge";
const PROTOCOL_VERSION = 1;

class SieveBridgeError extends Error {
  constructor(error) {
    super(error?.message || "Sieve Bridge request failed");
    this.name = "SieveBridgeError";
    this.code = error?.code || "UNKNOWN_ERROR";
    this.details = error?.details || {};
  }
}

class SieveBridgeClient {
  constructor() {
    this.port = null;
    this.pending = new Map();
    this.listeners = new Map();
    this.sequence = 0;
    this.hello = null;
  }

  static getInstance() {
    if (!SieveBridgeClient.instance)
      SieveBridgeClient.instance = new SieveBridgeClient();
    return SieveBridgeClient.instance;
  }

  async connect() {
    if (this.port)
      return this.hello;

    this.port = browser.runtime.connectNative(HOST_NAME);
    this.port.onMessage.addListener((message) => this.onMessage(message));
    this.port.onDisconnect.addListener(() => this.onDisconnect());

    try {
      this.hello = await this.request("bridge.hello");
      return this.hello;
    } catch (error) {
      this.disconnect();
      throw error;
    }
  }

  disconnect() {
    const port = this.port;
    this.port = null;
    this.hello = null;
    if (port) {
      try {
        port.disconnect();
      } catch (error) {
        // Port may already be disconnected.
      }
    }
  }

  onDisconnect() {
    const message = browser.runtime.lastError?.message || "Native Messaging host disconnected";
    const error = new SieveBridgeError({
      code: "BRIDGE_DISCONNECTED",
      message
    });

    for (const { reject } of this.pending.values())
      reject(error);
    this.pending.clear();

    for (const [socketId, handlers] of this.listeners.entries()) {
      handlers.onError?.({
        type: "SocketError",
        code: error.code,
        message: error.message
      });
      handlers.onClose?.({ reason: "bridge-disconnected" });
      this.listeners.delete(socketId);
    }

    this.port = null;
    this.hello = null;
  }

  onMessage(message) {
    if (!message || message.version !== PROTOCOL_VERSION)
      return;

    if (message.type === "response") {
      const pending = this.pending.get(message.id);
      if (!pending)
        return;
      this.pending.delete(message.id);
      if (message.ok)
        pending.resolve(message.result);
      else
        pending.reject(new SieveBridgeError(message.error));
      return;
    }

    if (message.type !== "event" || typeof message.socketId !== "string")
      return;

    const handlers = this.listeners.get(message.socketId);
    if (!handlers)
      return;

    if (message.event === "socket.data") {
      handlers.onData?.(SieveBridgeClient.base64ToBytes(message.payload?.data || ""));
      return;
    }
    if (message.event === "socket.error") {
      handlers.onError?.({
        type: "SocketError",
        ...(message.payload || {})
      });
      return;
    }
    if (message.event === "socket.close")
      handlers.onClose?.(message.payload || {});
  }

  async request(method, params = {}) {
    if (!this.port && method !== "bridge.hello")
      await this.connect();
    if (!this.port)
      throw new SieveBridgeError({
        code: "BRIDGE_NOT_CONNECTED",
        message: "Native Messaging host is not connected"
      });

    const id = `${Date.now().toString(36)}-${(++this.sequence).toString(36)}`;
    const promise = new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });

    try {
      this.port.postMessage({
        version: PROTOCOL_VERSION,
        type: "request",
        id,
        method,
        params
      });
    } catch (error) {
      this.pending.delete(id);
      throw error;
    }
    return await promise;
  }

  async createSocket(host, port, connectTimeoutMs = 15000) {
    const result = await this.request("socket.create", {
      host,
      port,
      connectTimeoutMs
    });
    return result.socketId;
  }

  setSocketHandlers(socketId, handlers) {
    this.listeners.set(socketId, handlers || {});
  }

  async connectSocket(socketId) {
    return await this.request("socket.connect", { socketId });
  }

  async startTLS(socketId) {
    return await this.request("socket.startTLS", { socketId });
  }

  async send(socketId, bytes) {
    return await this.request("socket.send", {
      socketId,
      data: SieveBridgeClient.bytesToBase64(bytes)
    });
  }

  async isAlive(socketId) {
    const result = await this.request("socket.isAlive", { socketId });
    return result.alive;
  }

  async disconnectSocket(socketId) {
    return await this.request("socket.disconnect", { socketId });
  }

  async destroySocket(socketId) {
    try {
      return await this.request("socket.destroy", { socketId });
    } finally {
      this.listeners.delete(socketId);
    }
  }

  async trustCertificate(securityInfo) {
    if (!securityInfo?.fingerprint256)
      throw new SieveBridgeError({
        code: "CERTIFICATE_FINGERPRINT_MISSING",
        message: "The certificate SHA-256 fingerprint is missing"
      });
    return await this.request("certificate.trust", {
      host: securityInfo.host,
      port: securityInfo.port,
      fingerprint256: securityInfo.fingerprint256
    });
  }

  static bytesToBase64(bytes) {
    const source = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    let binary = "";
    const chunkSize = 0x8000;
    for (let offset = 0; offset < source.length; offset += chunkSize) {
      binary += String.fromCharCode(...source.subarray(offset, offset + chunkSize));
    }
    return btoa(binary);
  }

  static base64ToBytes(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index++)
      bytes[index] = binary.charCodeAt(index);
    return Array.from(bytes);
  }
}

SieveBridgeClient.instance = null;

export { SieveBridgeClient, SieveBridgeError };
