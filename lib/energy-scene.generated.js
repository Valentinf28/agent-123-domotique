// Généré depuis ma-maison-portail-site/shared/energy-scene.js. Ne pas modifier à la main.
export const ENERGY_SCENE_GEOMETRY = {
  dawn: {
    width: 1704,
    height: 3692,
    inverter: { x: 842, y: 1880 },
    solarPanels: [{ x: 609, y: 1046 }, { x: 1313, y: 1174 }, { x: 1427, y: 1424 }, { x: 757, y: 1351 }],
    vehicleCable: {
      charger: { x: 613, y: 2190 }, cableStart: { x: 613, y: 2215 },
      descentControl: { x: 613, y: 2290 }, lowerRightControl: { x: 600, y: 2350 },
      bottomRight: { x: 570, y: 2385 }, bottomControl1: { x: 558, y: 2400 },
      bottomControl2: { x: 540, y: 2404 }, bottomLeft: { x: 525, y: 2402 },
      riseControl1: { x: 500, y: 2400 }, riseControl2: { x: 481, y: 2370 },
      riseMid: { x: 478, y: 2335 }, plugControl1: { x: 478, y: 2280 },
      plugControl2: { x: 468, y: 2210 }, vehiclePlug: { x: 450, y: 2197 },
    },
  },
  day: {
    width: 1704,
    height: 3692,
    inverter: { x: 842, y: 1880 },
    solarPanels: [{ x: 609, y: 1046 }, { x: 1313, y: 1174 }, { x: 1427, y: 1424 }, { x: 757, y: 1351 }],
    vehicleCable: {
      charger: { x: 613, y: 2190 }, cableStart: { x: 613, y: 2215 },
      descentControl: { x: 613, y: 2290 }, lowerRightControl: { x: 600, y: 2350 },
      bottomRight: { x: 570, y: 2385 }, bottomControl1: { x: 558, y: 2400 },
      bottomControl2: { x: 540, y: 2404 }, bottomLeft: { x: 525, y: 2402 },
      riseControl1: { x: 500, y: 2400 }, riseControl2: { x: 481, y: 2370 },
      riseMid: { x: 478, y: 2335 }, plugControl1: { x: 478, y: 2280 },
      plugControl2: { x: 468, y: 2210 }, vehiclePlug: { x: 450, y: 2197 },
    },
  },
  dusk: {
    width: 1704,
    height: 3692,
    inverter: { x: 842, y: 1880 },
    solarPanels: [{ x: 609, y: 1046 }, { x: 1313, y: 1174 }, { x: 1427, y: 1424 }, { x: 757, y: 1351 }],
    vehicleCable: {
      charger: { x: 613, y: 2190 }, cableStart: { x: 613, y: 2215 },
      descentControl: { x: 613, y: 2290 }, lowerRightControl: { x: 600, y: 2350 },
      bottomRight: { x: 570, y: 2385 }, bottomControl1: { x: 558, y: 2400 },
      bottomControl2: { x: 540, y: 2404 }, bottomLeft: { x: 525, y: 2402 },
      riseControl1: { x: 500, y: 2400 }, riseControl2: { x: 481, y: 2370 },
      riseMid: { x: 478, y: 2335 }, plugControl1: { x: 478, y: 2280 },
      plugControl2: { x: 468, y: 2210 }, vehiclePlug: { x: 450, y: 2197 },
    },
  },
  night: {
    width: 1706,
    height: 3688,
    inverter: { x: 843, y: 1880 },
    solarPanels: [{ x: 610, y: 1046 }, { x: 1314, y: 1174 }, { x: 1428, y: 1424 }, { x: 758, y: 1351 }],
    vehicleCable: {
      charger: { x: 614, y: 2190 }, cableStart: { x: 614, y: 2215 },
      descentControl: { x: 614, y: 2290 }, lowerRightControl: { x: 601, y: 2350 },
      bottomRight: { x: 571, y: 2385 }, bottomControl1: { x: 559, y: 2400 },
      bottomControl2: { x: 541, y: 2404 }, bottomLeft: { x: 526, y: 2402 },
      riseControl1: { x: 501, y: 2400 }, riseControl2: { x: 482, y: 2370 },
      riseMid: { x: 479, y: 2335 }, plugControl1: { x: 479, y: 2280 },
      plugControl2: { x: 469, y: 2210 }, vehiclePlug: { x: 451, y: 2197 },
    },
  },
};

export function projectCoverPoint(geometry, point, containerWidth, containerHeight) {
  if (!geometry || !point || containerWidth <= 0 || containerHeight <= 0) return { x: 0, y: 0 };
  const scale = Math.max(containerWidth / geometry.width, containerHeight / geometry.height);
  const renderedWidth = geometry.width * scale;
  const renderedHeight = geometry.height * scale;
  return {
    x: point.x * scale - (renderedWidth - containerWidth) / 2,
    y: point.y * scale - (renderedHeight - containerHeight) / 2,
  };
}

export function createEnergySceneLayout(period, containerWidth = 370, containerHeight = 630) {
  const geometry = ENERGY_SCENE_GEOMETRY[period] || ENERGY_SCENE_GEOMETRY.day;
  const horizontalScale = containerWidth / 370;
  const project = (point) => {
    const projected = projectCoverPoint(geometry, point, containerWidth, containerHeight);
    return { x: projected.x / horizontalScale, y: projected.y };
  };
  const inverterHub = project(geometry.inverter);
  const vehicleCable = Object.fromEntries(
    Object.entries(geometry.vehicleCable).map(([key, point]) => [key, project(point)]),
  );
  const horizontalOffset = inverterHub.x - 178;
  const verticalOffset = inverterHub.y - 329;
  const batteryConnectionY = 384 + verticalOffset;
  return {
    inverterHub,
    horizontalScale,
    verticalOffset,
    paths: {
      solar: `M${inverterHub.x} ${200 + verticalOffset} L${inverterHub.x} ${inverterHub.y}`,
      grid: `M${inverterHub.x} ${inverterHub.y} L${118 + horizontalOffset} ${inverterHub.y} L${118 + horizontalOffset} ${282 + verticalOffset} L22 ${282 + verticalOffset}`,
      home: `M${inverterHub.x} ${inverterHub.y} L${235 + horizontalOffset} ${inverterHub.y} L${235 + horizontalOffset} ${282 + verticalOffset} L260 ${282 + verticalOffset}`,
      battery: `M${inverterHub.x} ${inverterHub.y} L${inverterHub.x} ${batteryConnectionY}`,
      vehicle: `M${inverterHub.x} ${inverterHub.y} L${vehicleCable.charger.x} ${vehicleCable.charger.y} L${vehicleCable.cableStart.x} ${vehicleCable.cableStart.y} C${vehicleCable.descentControl.x} ${vehicleCable.descentControl.y} ${vehicleCable.lowerRightControl.x} ${vehicleCable.lowerRightControl.y} ${vehicleCable.bottomRight.x} ${vehicleCable.bottomRight.y} C${vehicleCable.bottomControl1.x} ${vehicleCable.bottomControl1.y} ${vehicleCable.bottomControl2.x} ${vehicleCable.bottomControl2.y} ${vehicleCable.bottomLeft.x} ${vehicleCable.bottomLeft.y} C${vehicleCable.riseControl1.x} ${vehicleCable.riseControl1.y} ${vehicleCable.riseControl2.x} ${vehicleCable.riseControl2.y} ${vehicleCable.riseMid.x} ${vehicleCable.riseMid.y} C${vehicleCable.plugControl1.x} ${vehicleCable.plugControl1.y} ${vehicleCable.plugControl2.x} ${vehicleCable.plugControl2.y} ${vehicleCable.vehiclePlug.x} ${vehicleCable.vehiclePlug.y}`,
    },
  };
}
