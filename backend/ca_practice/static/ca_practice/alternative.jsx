const { useState, useRef, useEffect, useLayoutEffect } = React;
//
// Split text into lines every N words
function wrapTextLines(text, wordsPerLine = 3) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const lines = [];
  for (let i = 0; i < words.length; i += wordsPerLine) {
    lines.push(words.slice(i, i + wordsPerLine).join(" "));
  }
  return lines.length ? lines : [""];
}

function AutoBox({
  text,
  centerX,
  centerY,
  label,
  fill = "white",
  textColor = "black",
  stroke = "black",
  onSizeChange,
  noWrap = false,
  layoutTick = 0,
}) {
  const textRef = useRef(null);
  const [size, setSize] = useState({ w: 140, h: 60 }); // default
  const [fontTick, setFontTick] = useState(0);

  const lines = noWrap ? [text] : wrapTextLines(text, 3);
  const lineHeight = 18;

  // Measure actual text size
  useLayoutEffect(() => {
    let frame = null;
    let t1 = null;
    let t2 = null;
    let t3 = null;
    const measure = () => {
      const paddingX = 20;
      const paddingY = 14;
      const fontSize = 14;
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.font = `${fontSize}px Manrope, system-ui, sans-serif`;
      const measuredLines = noWrap ? [text] : wrapTextLines(text, 3);
      const widths = measuredLines.map((line) => ctx.measureText(line).width);
      const maxWidth = widths.length ? Math.max(...widths) : 0;
      const height = measuredLines.length * lineHeight;
      const newSize = {
        w: maxWidth + paddingX * 2,
        h: height + paddingY * 2,
      };
      setSize(newSize);
      if (onSizeChange) onSizeChange(newSize);
    };
    frame = requestAnimationFrame(measure);
    t1 = setTimeout(measure, 100);
    t2 = setTimeout(measure, 300);
    t3 = setTimeout(measure, 600);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      if (t1) clearTimeout(t1);
      if (t2) clearTimeout(t2);
      if (t3) clearTimeout(t3);
    };
  }, [text, noWrap, fontTick, layoutTick]);

  useEffect(() => {
    let active = true;
    if (typeof document !== "undefined" && document.fonts?.ready) {
      document.fonts.ready.then(() => {
        if (active) {
          setFontTick((v) => v + 1);
        }
      });
    }
    return () => {
      active = false;
    };
  }, []);

  const rectX = centerX - size.w / 2;
  const rectY = centerY - size.h / 2;

  const firstLineY =
    centerY - ((lines.length - 1) * lineHeight) / 2;

  return (
    <g>
      {/* optional label above */}
      {label && (
        <text
          x={centerX}
          y={rectY - 10}
          textAnchor="middle"
          fontSize="14"
          fontWeight="bold"
        >
          {label}
        </text>
      )}

      <rect
        x={rectX}
        y={rectY}
        width={size.w}
        height={size.h}
        rx="10"
        ry="10"
        fill={fill}
        stroke={stroke}
        strokeWidth="2"
      />

      <text
        ref={textRef}
        textAnchor="middle"
        fontSize="14"
        dominantBaseline="middle"
        fill={textColor}
      >
        {lines.map((line, index) => (
          <tspan
            key={index}
            x={centerX}
            y={firstLineY + index * lineHeight}
          >
            {line}
          </tspan>
        ))}
      </text>
    </g>
  );
}

function App() {
  const defaults =
    (typeof window !== "undefined" && window.GRAPH_DEFAULTS_ALTERNATIVE) || {};
  const polarity = defaults.polarity ?? "green";
  const [layoutTick, setLayoutTick] = useState(0);

  const [xText, setXText] = useState(
    defaults.xText ??
    "This is the X box text and it will automatically wrap every five words."
  );
  const [xSize, setXSize] = useState(null);
  const [yText, setYText] = useState(
    defaults.yText ??
    "Here is the Y box text, which can also be quite long and will still fit into the box."
  );
  const [ySize, setYSize] = useState(null);
  const [zText, setZText] = useState(
    defaults.zText ??
    "This is the Z box text. It combines or depends on X and Y and will also wrap nicely."
  );
  const [zSize, setZSize] = useState(null);
  const [xToYLabel, setXToYLabel] = useState(defaults.xToYLabel ?? "X to Y");
  const [zToYLabel, setZToYLabel] = useState(defaults.zToYLabel ?? "Z to Y");
  const [zToYToXYFill, setZToYToXYFill] = useState(
    defaults.zToYToXYFill ?? "#ffd54f"
  );
  const [zToYToXYStroke, setZToYToXYStroke] = useState(
    defaults.zToYToXYStroke ?? "#f57f17"
  );
  const [xTopRightLabel, setXTopRightLabel] = useState(
    defaults.xTopRightLabel ?? "X note"
  );
  const [conclusionSize, setConclusionSize] = useState(null);
  const [xTopLeftLabel, setXTopLeftLabel] = useState(
    defaults.xTopLeftLabel ?? "X note L"
  );
  const [xMainLeftLabel, setXMainLeftLabel] = useState(
    defaults.xMainLeftLabel ?? "X main L"
  );

  useEffect(() => {
    const bump = () => setLayoutTick((v) => v + 1);
    if (typeof window !== "undefined") {
      window.addEventListener("load", bump);
      window.addEventListener("resize", bump);
      document.addEventListener("visibilitychange", bump);
      const t1 = setTimeout(bump, 100);
      const t2 = setTimeout(bump, 300);
      const t3 = setTimeout(bump, 600);
      return () => {
        window.removeEventListener("load", bump);
        window.removeEventListener("resize", bump);
        document.removeEventListener("visibilitychange", bump);
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
      };
    }
  }, []);

  const xCenter = 260;
  const xRenderCenter = xCenter + 40; // shift rendered X boxes and notes rightward
  const yCenter = 150;
  const yBoxCenter = 150;
  const xCopyCenterY = xSize
    ? yCenter - (xSize.h + 20)
    : yCenter - 80; // fallback before size is known
  const conclusionLeftX = xSize
    ? xRenderCenter - xSize.w / 2 - 12 + 8
    : xRenderCenter - 80;
  const conclusionCenterX = conclusionSize
    ? conclusionLeftX + conclusionSize.w / 2
    : conclusionLeftX + 60;
  const zCenterX = 220;
  const zCenterY = 340;

  let bigBox = null;
  if (xSize && ySize) {
    const paddingLeft = 94;
    const paddingRight = 24;
    const paddingY = 24;
    const xMin = Math.min(
      xCenter - xSize.w / 2,
      xRenderCenter - xSize.w / 2,
      580 - ySize.w / 2
    );
    const xMax = Math.max(
      xCenter + xSize.w / 2,
      xRenderCenter + xSize.w / 2,
      580 + ySize.w / 2
    );
    const yMin = Math.min(
      xCopyCenterY - xSize.h / 2,
      yCenter - xSize.h / 2,
      yBoxCenter - ySize.h / 2
    );
    const yMax = Math.max(
      xCopyCenterY + xSize.h / 2,
      yCenter + xSize.h / 2,
      yBoxCenter + ySize.h / 2
    );
    bigBox = {
      x: xMin - paddingLeft,
      y: yMin - paddingY,
      w: xMax - xMin + paddingLeft + paddingRight,
      h: yMax - yMin + paddingY * 2,
    };
  }

  let xToYArrow = null;
  if (xSize && ySize) {
    const yMid = yCenter;
    const startX = xRenderCenter + xSize.w / 2;
    const endX = 580 - ySize.w / 2;
    xToYArrow = {
      x1: startX,
      y1: yMid,
      x2: endX,
      y2: yMid,
    };
  }

  let bigBoxZ = null;
  if (zSize) {
    const paddingLeft = 24; // left padding
    const paddingRight = 200; // right padding
    const paddingY = 24; // vertical padding
    const xMin = zCenterX - zSize.w / 2;
    const xMax = zCenterX + zSize.w / 2;
    const yMin = zCenterY - zSize.h / 2;
    const yMax = zCenterY + zSize.h / 2;
    bigBoxZ = {
      x: xMin - paddingLeft,
      y: yMin - paddingY,
      w: xMax - xMin + paddingLeft + paddingRight,
      h: yMax - yMin + paddingY * 2,
    };
  }

  let zToYArrow = null;
  if (zSize && ySize) {
    const startX = zCenterX + zSize.w / 2; // right edge of Z box
    const startY = zCenterY;
    const endX = 580;
    const endY = yBoxCenter + ySize.h / 2;
    zToYArrow = { startX, startY, endX, endY };
  }

  let zLabelToXYArrow = null;
  if (zToYArrow && xToYArrow && bigBoxZ) {
    const labelX = (xToYArrow.x1 + xToYArrow.x2) / 2;
    const labelY = zToYArrow.startY - 8;
    const arrowTipOffset = 5; // negative raises tip (shorter), positive lowers (longer)
    const targetY = xToYArrow.y1 + arrowTipOffset;
    const headHeight = 14;
    const headHalfWidth = 16;
    const bodyHalfWidth = 8;
    const bodyTop = targetY + headHeight;
    const bodyBottom = bigBoxZ.y; // anchor to Z outer box top
    if (bodyBottom > bodyTop) {
      zLabelToXYArrow = {
        d: [
          `M ${labelX - bodyHalfWidth} ${bodyBottom}`,
          `L ${labelX + bodyHalfWidth} ${bodyBottom}`,
          `L ${labelX + bodyHalfWidth} ${bodyTop}`,
          `L ${labelX + headHalfWidth} ${bodyTop}`,
          `L ${labelX} ${targetY}`,
          `L ${labelX - headHalfWidth} ${bodyTop}`,
          `L ${labelX - bodyHalfWidth} ${bodyTop}`,
          "Z",
        ].join(" "),
        labelX,
        labelY,
      };
    }
  }

  let yBadge = null;
  if (ySize) {
    const isRed = polarity === "red";
    const badgeFill = isRed ? "#e53935" : "#4caf50";
    const badgeSymbol = isRed ? "-" : "+";
    const badgeOffsetX = -5; // relative to Y box right edge
    const badgeOffsetY = 2; // relative to Y box top edge
    const cx = 580 + ySize.w / 2 + badgeOffsetX;
    const cy = yBoxCenter - ySize.h / 2 + badgeOffsetY;
    yBadge = {
      cx,
      cy,
      r: 12,
      textY: cy + 5,
      textSize: 20,
      fill: badgeFill,
      symbol: badgeSymbol,
    };
  }

  return (
    <div>
      <div className="diagram-container">
        <svg width="100%" height="100%" viewBox="0 0 800 550">
          <g transform="translate(0,30)">
            <g className="diagram-ia">
            {/* Top row */}
            {/* Pink backdrop behind the big X/Y box, slight offset */}
            {bigBox && (
              <rect
                x={bigBox.x + 12}
                y={bigBox.y + 10}
                width={bigBox.w}
                height={bigBox.h}
                rx="14"
                ry="14"
                fill="rgb(191,191,191)"
                stroke="rgb(127,127,127)"
                strokeWidth="1"
              />
            )}

            {/* Big backdrop wrapping both X and Y */}
            {bigBox && (
              <rect
                x={bigBox.x}
                y={bigBox.y}
                width={bigBox.w}
                height={bigBox.h}
                rx="14"
                ry="14"
                fill="white"
                stroke="rgb(127,127,127)"
                strokeWidth="2"
              />
            )}
            {bigBox && (
              <text
                x={bigBox.x + 12}
                y={bigBox.y + 18}
                fontSize="14"
                fontWeight="bold"
                textAnchor="start"
              >
                Initial Argument
              </text>
            )}

            {/* Arrowhead definition */}
            <defs>
              <marker
                id="arrowhead"
                markerWidth="40"
                markerHeight="7"
                refX="10"
                refY="3.5"
                orient="auto"
              >
                <polygon points="0 0, 10 3.5, 0 7" />
              </marker>
              <marker
                id="arrowhead-red"
                markerWidth="40"
                markerHeight="7"
                refX="10"
                refY="3.5"
                orient="auto"
              >
                <polygon points="0 0, 10 3.5, 0 7" fill="rgb(187, 39, 71)" />
              </marker>
            </defs>

            <AutoBox
              text={xText}
              centerX={xRenderCenter}
              centerY={yCenter}
              // label="X"
              onSizeChange={setXSize}
              layoutTick={layoutTick}
            />
            {xSize && bigBox && (
              <text
                x={Math.max(bigBox.x + 12, xRenderCenter - xSize.w / 2 - 12)}
                y={yCenter}
                fontSize="18"
                fontStyle="italic"
                dominantBaseline="middle"
                textAnchor="end"
              >
                {xMainLeftLabel}
              </text>
            )}
            {xSize && (
              <AutoBox
                text={xTopRightLabel}
                centerX={conclusionCenterX}
                centerY={xCopyCenterY}
                onSizeChange={setConclusionSize}
                noWrap
                layoutTick={layoutTick}
              />
            )}
            {xSize && bigBox && (
              <text
                x={Math.max(bigBox.x + 12, xRenderCenter - xSize.w / 2 - 12)}
                y={xCopyCenterY}
                fontSize="18"
                fontStyle="italic"
                dominantBaseline="middle"
                textAnchor="end"
              >
                {xTopLeftLabel}
              </text>
            )}
            <AutoBox
              text={yText}
              centerX={580}
              centerY={yBoxCenter}
              // label="Y"
              onSizeChange={setYSize}
              layoutTick={layoutTick}
            />
            {yBadge && (
              <g>
                <circle
                  cx={yBadge.cx}
                  cy={yBadge.cy}
                  r={yBadge.r}
                  fill={yBadge.fill}
                />
                <text
                  x={yBadge.cx}
                  y={yBadge.textY}
                  fontSize={yBadge.textSize}
                  fontWeight="bold"
                  fill="white"
                  textAnchor="middle"
                >
                  {yBadge.symbol}
                </text>
              </g>
            )}

            {/* X -> Y horizontal arrow, hugs box edges */}
            {xToYArrow && (
              <line
                x1={xToYArrow.x1}
                y1={xToYArrow.y1}
                x2={xToYArrow.x2}
                y2={xToYArrow.y2}
                stroke="black"
                strokeWidth="2"
                markerEnd="url(#arrowhead)"
              />
            )}
            {xToYArrow && (
              <text
                x={(xToYArrow.x1 + xToYArrow.x2) / 2}
                y={xToYArrow.y1 - 10}
                textAnchor="middle"
                fontSize="14"
              >
                {xToYLabel}
              </text>
            )}

            </g>
            <g className="diagram-ca">
            {/* Bottom center */}
            {/* Pink backdrop behind Z box, slight offset */}
            {bigBoxZ && (
              <rect
                x={bigBoxZ.x + 12}
                y={bigBoxZ.y + 10}
                width={bigBoxZ.w}
                height={bigBoxZ.h}
                rx="14"
                ry="14"
                fill="rgb(244, 182, 204)"
                // stroke="lightgreen"
                strokeWidth="1"
              />
            )}

            {/* Big backdrop around Z */}
            {bigBoxZ && (
              <rect
                x={bigBoxZ.x}
                y={bigBoxZ.y}
                width={bigBoxZ.w}
                height={bigBoxZ.h}
                rx="14"
                ry="14"
                fill="rgb(253, 244, 247)"
                stroke="rgb(242, 167, 193)"
                strokeWidth="2"
              />
            )}
            {bigBoxZ && (
              <text
                x={bigBoxZ.x + 12}
                y={bigBoxZ.y + 18}
                fontSize="14"
                fontWeight="bold"
                textAnchor="start"
                fill="rgb(187,39,71)"
              >
                Counter-argument
              </text>
            )}

            <g className="diagram-ca-detail">
              <AutoBox
                text={zText}
                centerX={zCenterX}
                centerY={zCenterY}
                // label="Z"
                onSizeChange={setZSize}
                fill="rgb(253,244,247)"
                stroke="rgb(187,39,71)"
                textColor="rgb(187,39,71)"
                layoutTick={layoutTick}
              />
            </g>

            {/* Z -> Y routed arrow: right, then up to Y bottom edge */}
            {zToYArrow && (
              <g className="diagram-ca-detail">
                <path
                  d={`M ${zToYArrow.startX} ${zToYArrow.startY} H ${zToYArrow.endX} V ${zToYArrow.endY}`}
                  fill="none"
                  stroke="rgb(187, 39, 71)"
                  strokeWidth="2"
                  markerEnd="url(#arrowhead-red)"
                />
                <text
                  x={(zToYArrow.startX + zToYArrow.endX) / 2}
                  y={zToYArrow.startY - 8}
                  textAnchor="middle"
                  fontSize="14"
                  fill="rgb(187, 39, 71)"
                >
                  {zToYLabel}
                </text>
              </g>
            )}

            {/* Arrow from Z→Y label up to X→Y arrow */}
            {zLabelToXYArrow && (
              <path
                d={zLabelToXYArrow.d}
                fill="rgb(242,167,193)"
                stroke="rgb(237,112,153)"
                strokeWidth="2"
                className="diagram-ca-highlight"
              />
            )}

                      </g>
          </g>
        </svg>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root_alternative")).render(<App />);
