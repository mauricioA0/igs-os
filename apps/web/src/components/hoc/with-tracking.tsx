"use client";

import { createContext, useContext, type ComponentType, type MouseEvent, type ReactNode } from "react";
import { displayNameOf } from "./display-name";

/** Product analytics without PII: event names + small enum-like properties only. */
export type TrackFn = (event: string, properties?: Record<string, string | number | boolean>) => void;

const noop: TrackFn = () => {};
const TrackingContext = createContext<TrackFn>(noop);

export function TrackingProvider({ track, children }: { track: TrackFn; children: ReactNode }) {
  return <TrackingContext.Provider value={track}>{children}</TrackingContext.Provider>;
}

export function useTrack(): TrackFn {
  return useContext(TrackingContext);
}

type Clickable = { onClick?: (event: MouseEvent<HTMLElement>) => void };

/** Fires `event` on click (demo-tour steps, key CTAs), then calls the component's own onClick. */
export function withTracking<P extends Clickable>(
  Component: ComponentType<P>,
  opts: { event: string; properties?: (props: P) => Record<string, string | number | boolean> },
) {
  function WithTracking(props: P) {
    const track = useTrack();
    const onClick = (e: MouseEvent<HTMLElement>) => {
      track(opts.event, opts.properties?.(props));
      props.onClick?.(e);
    };
    return <Component {...props} onClick={onClick} />;
  }
  WithTracking.displayName = `withTracking(${displayNameOf(Component as ComponentType<never>)})`;
  return WithTracking;
}
