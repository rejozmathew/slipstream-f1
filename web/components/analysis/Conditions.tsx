import { utcOffsetLabel } from "../../domain/format";
import type { RaceState } from "../../domain/protocol";
import { DataValue } from "../shared/DataValue";
import { Panel } from "../shared/Panel";

export function Conditions({ weather, session }: { weather: RaceState["weather"]; session: RaceState["session"] }) {
  const rain = weather.rainfall === true ? "RAIN DETECTED" : weather.rainfall === false ? "NO RAIN" : null;
  return (
    <Panel eyebrow="WEATHER FEED" title="Conditions" action={rain ? <span className="condition-badge">{rain}</span> : undefined} className="conditions-panel">
      <div className="conditions-grid">
        <div><span>TRACK</span><DataValue value={weather.track_temperature == null ? null : `${weather.track_temperature.toFixed(1)} C`} availability={weather.availability.track_temperature} /></div>
        <div><span>AIR</span><DataValue value={weather.air_temperature == null ? null : `${weather.air_temperature.toFixed(1)} C`} availability={weather.availability.air_temperature} /></div>
        <div><span>HUMIDITY</span><DataValue value={weather.humidity == null ? null : `${weather.humidity.toFixed(0)}%`} availability={weather.availability.humidity} /></div>
        <div><span>WIND</span><DataValue value={weather.wind_speed == null ? null : `${weather.wind_speed.toFixed(1)} m/s`} availability={weather.availability.wind_speed} /></div>
        <div><span>PRESSURE</span><DataValue value={weather.pressure == null ? null : `${weather.pressure.toFixed(1)} hPa`} availability={weather.availability.pressure} /></div>
        <div><span>TRACK LOCAL</span><DataValue value={session.local_time ? `${session.local_time.slice(11, 19)} ${utcOffsetLabel(session.gmt_offset)}` : null} /></div>
      </div>
      <footer className="panel-footer">RAIN IS A SENSOR OBSERVATION · SURFACE GRIP IS NOT INFERRED</footer>
    </Panel>
  );
}
