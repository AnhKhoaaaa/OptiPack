import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { PackingPlan, PlacedItem } from "../types/contract";
import { mapPlacementToThreeJSFloor } from "../utils/coordinateTransform";

interface PackingViewer3DProps {
  plan: PackingPlan;
}

export const PackingViewer3D: React.FC<PackingViewer3DProps> = ({ plan }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const [currentStep, setCurrentStep] = useState<number>(plan.placements.length);

  const totalSteps = plan.placements.length;

  useEffect(() => {
    setCurrentStep(plan.placements.length);
  }, [plan]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 600;
    const height = 420;

    // 1. Three.js Scene, Camera, Renderer
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a); // Deep slate dark mode

    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 2000);
    camera.position.set(380, 320, 480);
    camera.lookAt(0, 60, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // 2. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight.position.set(200, 400, 250);
    dirLight.castShadow = true;
    scene.add(dirLight);

    // 3. Grid Helper
    const grid = new THREE.GridHelper(800, 20, 0x334155, 0x1e293b);
    grid.position.y = -1;
    scene.add(grid);

    // 4. Carton Wireframe
    const cartonDims = plan.carton.internal_dimensions_mm;
    const cartonGeo = new THREE.BoxGeometry(
      cartonDims.length_mm,
      cartonDims.height_mm,
      cartonDims.width_mm
    );
    const wireGeo = new THREE.EdgesGeometry(cartonGeo);
    const wireMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, linewidth: 2 });
    const cartonWire = new THREE.LineSegments(wireGeo, wireMat);
    cartonWire.position.set(0, cartonDims.height_mm / 2, 0);
    scene.add(cartonWire);

    // 5. Carton Floor Plane
    const floorGeo = new THREE.PlaneGeometry(cartonDims.length_mm, cartonDims.width_mm);
    floorGeo.rotateX(-Math.PI / 2);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.8,
      metalness: 0.2,
    });
    const floorMesh = new THREE.Mesh(floorGeo, floorMat);
    floorMesh.position.y = 0;
    scene.add(floorMesh);

    // 6. Placed Items up to current step
    const itemGroup = new THREE.Group();
    const visiblePlacements = plan.placements.filter((p) => p.step_number <= currentStep);

    visiblePlacements.forEach((p) => {
      const transform = mapPlacementToThreeJSFloor(plan.carton, p);
      const [w, h, d] = transform.size;
      const [x, y, z] = transform.position;

      const boxGeo = new THREE.BoxGeometry(w, h, d);
      const boxMat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(p.display_color_hex || "#3b82f6"),
        roughness: 0.3,
        metalness: 0.1,
        transparent: true,
        opacity: 0.92,
      });
      const mesh = new THREE.Mesh(boxGeo, boxMat);
      mesh.position.set(x, y, z);

      // Edges highlight
      const edges = new THREE.EdgesGeometry(boxGeo);
      const lineMat = new THREE.LineBasicMaterial({ color: 0xffffff, linewidth: 1 });
      const line = new THREE.LineSegments(edges, lineMat);
      mesh.add(line);

      itemGroup.add(mesh);
    });

    scene.add(itemGroup);

    // Subtle continuous rotation for 3D depth perception
    let animationFrameId: number;
    let angle = 0;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      angle += 0.003;
      const radius = 600;
      camera.position.x = Math.sin(angle) * radius;
      camera.position.z = Math.cos(angle) * radius;
      camera.lookAt(0, cartonDims.height_mm / 3, 0);
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      renderer.dispose();
      if (container) container.innerHTML = "";
    };
  }, [plan, currentStep]);

  const activeItem = plan.placements.find((p) => p.step_number === currentStep);

  return (
    <div className="card viewer-card">
      <div className="card-header">
        <h2>3. 3D Packing Visualization & Sequence</h2>
        <span className="badge badge-success">
          {plan.carton.carton_id} ({plan.carton.display_name})
        </span>
      </div>

      <div className="viewport-container" ref={mountRef}></div>

      <div className="step-controls">
        <div className="step-slider-header">
          <span>
            <strong>Packing Step:</strong> {currentStep} / {totalSteps}
          </span>
          {activeItem && (
            <span className="step-item-info">
              Current: <strong>{activeItem.display_name}</strong> (Rotation:{" "}
              <code>{activeItem.rotation_code}</code>, Pos: [{activeItem.position_mm.x},{" "}
              {activeItem.position_mm.y}, {activeItem.position_mm.z}])
            </span>
          )}
        </div>

        <input
          type="range"
          min={1}
          max={Math.max(1, totalSteps)}
          value={currentStep}
          onChange={(e) => setCurrentStep(parseInt(e.target.value) || 1)}
          className="step-slider"
        />

        <div className="step-btn-bar">
          <button
            className="btn btn-sm"
            onClick={() => setCurrentStep((prev) => Math.max(1, prev - 1))}
            disabled={currentStep <= 1}
          >
            ← Previous Step
          </button>
          <button
            className="btn btn-sm"
            onClick={() => setCurrentStep((prev) => Math.min(totalSteps, prev + 1))}
            disabled={currentStep >= totalSteps}
          >
            Next Step →
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => setCurrentStep(totalSteps)}
          >
            Show All Steps
          </button>
        </div>
      </div>
    </div>
  );
};
