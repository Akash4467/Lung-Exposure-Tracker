/** Line icons for the tab bar, drawn with SVG (no icon font needed). 24×24 grid. */
import Svg, { Circle, Line, Path, Polyline, Rect } from 'react-native-svg';

export type TabIconName = 'today' | 'tomorrow' | 'map' | 'trends' | 'settings';

const STROKE = 1.8;

/** A cog: eight teeth around a ring, built from points so it stays crisp at any size. */
const GEAR = (() => {
  const pts: string[] = [];
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2 - Math.PI / 16;
    const r = i % 2 === 0 ? 9.6 : 7.4;
    pts.push(`${(12 + r * Math.cos(a)).toFixed(2)} ${(12 + r * Math.sin(a)).toFixed(2)}`);
  }
  return `M ${pts.join(' L ')} Z`;
})();

export function TabIcon({ name, color, size = 24 }: { name: TabIconName; color: string; size?: number }) {
  const p = { stroke: color, strokeWidth: STROKE, strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none' } as const;
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {name === 'today' ? (
        <>
          {/* moving air */}
          <Path d="M3 8h9.5a2.5 2.5 0 1 0-2.5-2.5" {...p} />
          <Path d="M3 12h14.5a3 3 0 1 1-3 3" {...p} />
          <Path d="M3 16h6" {...p} />
        </>
      ) : name === 'tomorrow' ? (
        <>
          <Rect x={3.5} y={5} width={17} height={15.5} rx={3.5} {...p} />
          <Line x1={3.5} y1={10} x2={20.5} y2={10} {...p} />
          <Line x1={8} y1={3} x2={8} y2={7} {...p} />
          <Line x1={16} y1={3} x2={16} y2={7} {...p} />
          <Circle cx={12} cy={15} r={1.2} fill={color} />
        </>
      ) : name === 'trends' ? (
        <>
          <Polyline points="3,17 9,11 13,15 21,7" {...p} />
          <Polyline points="15.5,7 21,7 21,12.5" {...p} />
        </>
      ) : name === 'map' ? (
        <>
          {/* a folded paper map */}
          <Path d="M3 6.5l5-2 8 3 5-2v12l-5 2-8-3-5 2z" {...p} />
          <Line x1={8} y1={4.5} x2={8} y2={16.5} {...p} />
          <Line x1={16} y1={7.5} x2={16} y2={19.5} {...p} />
        </>
      ) : (
        <>
          <Path d={GEAR} {...p} />
          <Circle cx={12} cy={12} r={3} {...p} />
        </>
      )}
    </Svg>
  );
}
