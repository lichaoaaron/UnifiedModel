import { AppEvents } from '@grafana/data';
import { getAppEvents } from '@grafana/runtime';
import { formatError } from '../lib/json';

/** Publish a success toast through Grafana's app events. */
export function notifySuccess(message: string): void {
  getAppEvents().publish({ type: AppEvents.alertSuccess.name, payload: [message] });
}

/** Publish an error toast. Accepts a title and an optional error/detail. */
export function notifyError(title: string, err?: unknown): void {
  const detail = err === undefined ? undefined : formatError(err);
  getAppEvents().publish({
    type: AppEvents.alertError.name,
    payload: detail ? [title, detail] : [title],
  });
}
