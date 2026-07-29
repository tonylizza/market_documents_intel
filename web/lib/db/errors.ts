/**
 * Typed, redaction-safe error classes for the database access layer.
 * Every error message here is written assuming it might reach a log line
 * or (in dev) a rendered error boundary -- never include a connection
 * string, password, or raw driver stack in a message.
 */

export class DatabaseConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DatabaseConfigError";
  }
}

export class DatabaseUnavailableError extends Error {
  constructor(message = "The application database is currently unavailable.") {
    super(message);
    this.name = "DatabaseUnavailableError";
  }
}

export class QueryTimeoutError extends Error {
  constructor(message = "The database query took too long to complete.") {
    super(message);
    this.name = "QueryTimeoutError";
  }
}

export class MalformedRowError extends Error {
  constructor(context: string, message: string) {
    super(`Malformed row from ${context}: ${message}`);
    this.name = "MalformedRowError";
  }
}

/** Node/pg error codes that indicate the server is unreachable, as opposed
 * to a query-specific failure. See https://node-postgres.com/api/client. */
const CONNECTION_ERROR_CODES = new Set([
  "ECONNREFUSED",
  "ENOTFOUND",
  "ETIMEDOUT",
  "EHOSTUNREACH",
]);

/**
 * Translate a raw driver/network error into one of this module's typed
 * errors. Never rethrows the original error object (which may carry a
 * connection string on some driver versions) -- always a fresh Error with
 * a redacted, generic message.
 */
export function toApplicationError(error: unknown): Error {
  if (error instanceof DatabaseConfigError || error instanceof DatabaseUnavailableError || error instanceof QueryTimeoutError || error instanceof MalformedRowError) {
    return error;
  }

  const code = (error as { code?: string } | undefined)?.code;
  if (code === "57014" || code === "ETIMEDOUT") {
    return new QueryTimeoutError();
  }
  if (code && CONNECTION_ERROR_CODES.has(code)) {
    return new DatabaseUnavailableError();
  }
  return new DatabaseUnavailableError();
}
