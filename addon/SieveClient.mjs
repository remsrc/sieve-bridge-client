/*
 * The content of this file is licensed. You may obtain a copy of
 * the license at https://github.com/thsmi/sieve/ or request it via
 * email from the author.
 *
 * Do not remove or change this comment.
 *
 * The initial author of the code is:
 *   Thomas Schmid <schmid-thomas@gmx.net>
 */

import {
  SieveAbstractClient,
  TLS_SECURITY_EXPLICIT
} from "./SieveAbstractClient.mjs";

import {
  SieveCertValidationException,
  SieveClientException,
  SieveException
} from "./SieveExceptions.mjs";

import { SieveUrl } from "./SieveUrl.mjs";
import { SieveBridgeClient, SieveBridgeError } from "./SieveBridgeClient.mjs";

/**
 * ManageSieve client using the platform-independent Native Messaging bridge.
 */
class SieveNativeClient extends SieveAbstractClient {
  constructor(...args) {
    super(...args);
    this.bridge = SieveBridgeClient.getInstance();
    this.closing = false;
    this.alive = false;
  }

  isAlive() {
    return super.isAlive(this) && this.alive && !this.closing;
  }

  async startTLS() {
    await super.startTLS();
    this.getLogger().logState("[SieveClient:startTLS()] Upgrading through Native Messaging bridge");

    try {
      await this.bridge.startTLS(this.socket);
    } catch (error) {
      if (error instanceof SieveBridgeError &&
          ["CERT_VALIDATION_FAILED", "CERTIFICATE_CHANGED"].includes(error.code)) {
        throw new SieveCertValidationException(error.details);
      }
      throw new SieveClientException(error.message);
    }

    this.secured = true;
  }

  async connect(url) {
    if (this.socket)
      return this;

    if (typeof url === "string" || url instanceof String)
      url = new SieveUrl(url);

    this.host = url.getHost();
    this.port = url.getPort();
    this.security = TLS_SECURITY_EXPLICIT;
    this.closing = false;
    this.alive = false;

    this.getLogger().logState(`Connecting through Sieve Bridge to ${this.host}:${this.port} ...`);

    try {
      this.socket = await this.bridge.createSocket(
        this.host,
        this.port,
        this.getTimeoutWait()
      );

      this.bridge.setSocketHandlers(this.socket, {
        onData: (bytes) => this.onData(bytes),
        onError: async (error) => {
          this.alive = false;
          let exception;
          if (error?.type === "CertValidationError")
            exception = new SieveCertValidationException(error);
          else if (error?.type === "SocketError")
            exception = new SieveClientException(error.message);
          else
            exception = new SieveException("Socket failed without providing an error code.");

          if (this.listener?.onError)
            await this.listener.onError(exception);
        },
        onClose: async () => {
          this.alive = false;
          if (this.closing)
            return;
          this.getLogger().logState(`SieveClient: OnClose (${this.host}:${this.port})`);
          await this.disconnect(new Error("Server closed connection unexpectedly"));
        }
      });

      await this.bridge.connectSocket(this.socket);
      this.alive = true;
    } catch (error) {
      const socket = this.socket;
      this.socket = null;
      this.alive = false;
      if (socket) {
        try {
          await this.bridge.destroySocket(socket);
        } catch (cleanupError) {
          // Preserve the connection error.
        }
      }
      if (error instanceof SieveBridgeError)
        throw new SieveClientException(error.message);
      throw error;
    }

    return this;
  }

  async destroy() {
    if (!this.socket)
      return;
    this.closing = true;
    this.alive = false;
    const socket = this.socket;
    this.socket = null;
    try {
      await this.bridge.destroySocket(socket);
    } finally {
      this.closing = false;
    }
  }

  onSend(data) {
    const output = (new TextEncoder()).encode(data);

    if (this.getLogger().isLevelStream())
      this.getLogger().logStream(`Client -> Server [Byte Array]:\n${Array.from(output)}`);

    this.bridge.send(this.socket, output).catch(async (error) => {
      if (this.listener?.onError)
        await this.listener.onError(new SieveClientException(error.message));
    });
  }
}

export { SieveNativeClient as Sieve };
