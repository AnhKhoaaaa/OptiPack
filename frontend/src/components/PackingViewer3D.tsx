import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PackingPlan, PlacedItem } from "../types/contract";
import { mapPlacementToThreeJSFloor } from "../utils/coordinateTransform";

interface PackingViewer3DProps {
  plan: PackingPlan;
}

type CameraPreset = "iso" | "top" | "front" | "side";

export const PackingViewer3D: React.FC<PackingViewer3DProps> = ({ plan }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);

  const [currentStep, setCurrentStep] = useState<number>(plan.placements.length);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [showSafetyHalo, setShowSafetyHalo] = useState<boolean>(true);
  const [autoRotate, setAutoRotate] = useState<boolean>(false);
  const [activePreset, setActivePreset] = useState<CameraPreset>("iso");

  const totalSteps = plan.placements.length;

  // Sync step count on plan change
  useEffect(() => {
    setCurrentStep(plan.placements.length);
    setIsPlaying(false);
  }, [plan]);

  // Auto-play timer
  useEffect(() => {
    if (!isPlaying) return;

    const timer = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= totalSteps) {
          setIsPlaying(false);
          return totalSteps;
        }
        return prev + 1;
      });
    }, 1200);

    return () => clearInterval(timer);
  }, [isPlaying, totalSteps]);

  // Camera preset handler
  const setCameraView = (preset: CameraPreset) => {
    setActivePreset(preset);
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;

    const cartonDims = plan.carton.internal_dimensions_mm;
    const targetY = cartonDims.height_mm / 2;
    controls.target.set(0, targetY, 0);

    switch (preset) {
      case "iso":
        camera.position.set(380, 320, 480);
        break;
      case "top":
        camera.position.set(0, 680, 1); // Slight offset on Z to prevent gimbal lock
        break;
      case "front":
        camera.position.set(0, targetY, 560);
        break;
      case "side":
        camera.position.set(560, targetY, 0);
        break;
    }
    controls.update();
  };

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 600;
    const height = 440;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0f1d); // Sleek deep space dark mode

    const cartonDims = plan.carton.internal_dimensions_mm;
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 3000);
    camera.position.set(380, 320, 480);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // 2. OrbitControls (Mouse drag to rotate, scroll to zoom, right click to pan)
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.maxPolarAngle = Math.PI / 2 + 0.12; // Prevent going deeply underground
    controls.minDistance = 150;
    controls.maxDistance = 1400;
    controls.target.set(0, cartonDims.height_mm / 2, 0);
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 1.2;
    controlsRef.current = controls;

    // 3. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight1.position.set(250, 450, 300);
    dirLight1.castShadow = true;
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x38bdf8, 0.35); // Subtle cyan fill
    dirLight2.position.set(-300, 150, -200);
    scene.add(dirLight2);

    // 4. Ground Grid
    const grid = new THREE.GridHelper(900, 30, 0x1e293b, 0x0f172a);
    grid.position.y = -1;
    scene.add(grid);

    // 5. Carton Wireframe
    const cartonGeo = new THREE.BoxGeometry(
      cartonDims.length_mm,
      cartonDims.height_mm,
      cartonDims.width_mm
    );
    const wireGeo = new THREE.EdgesGeometry(cartonGeo);
    const wireMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8, // OptiPack Cyan
      linewidth: 2,
    });
    const cartonWire = new THREE.LineSegments(wireGeo, wireMat);
    cartonWire.position.set(0, cartonDims.height_mm / 2, 0);
    scene.add(cartonWire);

    // 6. Carton Floor Surface
    const floorGeo = new THREE.PlaneGeometry(cartonDims.length_mm, cartonDims.width_mm);
    floorGeo.rotateX(-Math.PI / 2);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x111c30,
      roughness: 0.85,
      metalness: 0.15,
    });
    const floorMesh = new THREE.Mesh(floorGeo, floorMat);
    floorMesh.position.y = 0;
    scene.add(floorMesh);

    // 7. Placed Items up to current step
    const itemGroup = new THREE.Group();
    const visiblePlacements = plan.placements.filter((p) => p.step_number <= currentStep);

    visiblePlacements.forEach((p) => {
      const transform = mapPlacementToThreeJSFloor(plan.carton, p);
      const [wPlaced, hPlaced, dPlaced] = transform.size; // placed dimensions (with margin)
      const [x, y, z] = transform.position;

      const isCurrentActive = p.step_number === currentStep;

      if (showSafetyHalo) {
        // A. Nominal Inner Solid Box
        const nomDx = p.nominal_dimensions_mm.dx;
        const nomDy = p.nominal_dimensions_mm.dy;
        const nomDz = p.nominal_dimensions_mm.dz;

        // Determine orientation scaling based on placed dimensions
        const innerGeo = new THREE.BoxGeometry(
          Math.min(nomDx, wPlaced),
          Math.min(nomDz, hPlaced),
          Math.min(nomDy, dPlaced)
        );
        const innerMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(p.display_color_hex || "#3b82f6"),
          roughness: 0.35,
          metalness: 0.1,
          transparent: true,
          opacity: 0.94,
        });
        const innerMesh = new THREE.Mesh(innerGeo, innerMat);
        innerMesh.position.set(x, y, z);
        innerMesh.castShadow = true;
        innerMesh.receiveShadow = true;

        const innerEdges = new THREE.EdgesGeometry(innerGeo);
        const innerLineMat = new THREE.LineBasicMaterial({
          color: 0xffffff,
          linewidth: 1,
        });
        innerMesh.add(new THREE.LineSegments(innerEdges, innerLineMat));
        itemGroup.add(innerMesh);

        // B. Translucent Safety Buffer Halo (+Safety Margin)
        const haloGeo = new THREE.BoxGeometry(wPlaced, hPlaced, dPlaced);
        const haloEdges = new THREE.EdgesGeometry(haloGeo);
        const haloLineMat = new THREE.LineBasicMaterial({
          color: isCurrentActive ? 0xfacc15 : 0x94a3b8, // Amber for active step, slate for past
          transparent: true,
          opacity: 0.55,
        });
        const haloWire = new THREE.LineSegments(haloEdges, haloLineMat);
        haloWire.position.set(x, y, z);
        itemGroup.add(haloWire);
      } else {
        // Standard Solid Box
        const boxGeo = new THREE.BoxGeometry(wPlaced, hPlaced, dPlaced);
        const boxMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(p.display_color_hex || "#3b82f6"),
          roughness: 0.3,
          metalness: 0.1,
          transparent: true,
          opacity: isCurrentActive ? 0.98 : 0.88,
        });
        const mesh = new THREE.Mesh(boxGeo, boxMat);
        mesh.position.set(x, y, z);
        mesh.castShadow = true;
        mesh.receiveShadow = true;

        const edges = new THREE.EdgesGeometry(boxGeo);
        const lineMat = new THREE.LineBasicMaterial({
          color: isCurrentActive ? 0xfacc15 : 0xffffff,
          linewidth: isCurrentActive ? 2 : 1,
        });
        mesh.add(new THREE.LineSegments(edges, lineMat));
        itemGroup.add(mesh);
      }
    });

    scene.add(itemGroup);

    // 8. Animation & Render Loop
    let animationFrameId: number;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // 9. Resize observer for responsive layout
    const handleResize = () => {
      if (!container) return;
      const newWidth = container.clientWidth;
      camera.aspect = newWidth / height;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, height);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
      controls.dispose();
      renderer.dispose();
      if (container) container.innerHTML = "";
    };
  }, [plan, currentStep, showSafetyHalo, autoRotate]);

  const activeItem = plan.placements.find((p) => p.step_number === currentStep);

  return (
    <div className="card viewer-card">
      <div className="card-header">
        <div className="viewer-title-group">
          <h2>3. Interactive 3D Packing Viewport</h2>
          <span className="badge badge-success">
            {plan.carton.carton_id} ({plan.carton.display_name})
          </span>
        </div>

        {/* Camera Presets & Halo Toggle */}
        <div className="viewer-actions-top">
          <div className="btn-group-pill">
            <button
              className={`btn-pill ${activePreset === "iso" ? "active" : ""}`}
              onClick={() => setCameraView("iso")}
              title="Isometric 3D Perspective"
            >
              Iso
            </button>
            <button
              className={`btn-pill ${activePreset === "top" ? "active" : ""}`}
              onClick={() => setCameraView("top")}
              title="Top-Down Orthographic View"
            >
              Top
            </button>
            <button
              className={`btn-pill ${activePreset === "front" ? "active" : ""}`}
              onClick={() => setCameraView("front")}
              title="Front Elevation View"
            >
              Front
            </button>
            <button
              className={`btn-pill ${activePreset === "side" ? "active" : ""}`}
              onClick={() => setCameraView("side")}
              title="Side Elevation View"
            >
              Side
            </button>
          </div>

          <label className="checkbox-halo-toggle" title="Show +5mm Uncertainty Buffer Halo">
            <input
              type="checkbox"
              checked={showSafetyHalo}
              onChange={(e) => setShowSafetyHalo(e.target.checked)}
            />
            <span>Safety Buffer Halo</span>
          </label>

          <button
            className={`btn-pill ${autoRotate ? "active" : ""}`}
            onClick={() => setAutoRotate((prev) => !prev)}
            title="Auto-rotate turntable"
          >
            {autoRotate ? "Turntable ON" : "Turntable"}
          </button>
        </div>
      </div>

      {/* Three.js Canvas Container */}
      <div className="viewport-container" ref={mountRef}></div>

      {/* Step Sequence Controls */}
      <div className="step-controls">
        <div className="step-slider-header">
          <div className="step-badge-counter">
            <span className="step-counter-tag">
              Step {currentStep} of {totalSteps}
            </span>
            {activeItem && (
              <span className="step-item-name" style={{ color: activeItem.display_color_hex || "#38bdf8" }}>
                <strong>{activeItem.display_name}</strong>
              </span>
            )}
          </div>

          {activeItem && (
            <div className="step-item-info">
              <span>Rot: <code>{activeItem.rotation_code}</code></span>
              <span>Pos: <code>[{activeItem.position_mm.x}, {activeItem.position_mm.y}, {activeItem.position_mm.z}] mm</code></span>
              <span>Support: <code>{Math.round(activeItem.support_ratio * 100)}%</code></span>
            </div>
          )}
        </div>

        <input
          type="range"
          min={1}
          max={Math.max(1, totalSteps)}
          value={currentStep}
          onChange={(e) => {
            setCurrentStep(parseInt(e.target.value) || 1);
            setIsPlaying(false);
          }}
          className="step-slider"
        />

        <div className="step-btn-bar">
          <button
            className={`btn btn-sm ${isPlaying ? "btn-warning" : "btn-primary"}`}
            onClick={() => {
              if (isPlaying) {
                setIsPlaying(false);
              } else {
                if (currentStep >= totalSteps) setCurrentStep(1);
                setIsPlaying(true);
              }
            }}
          >
            {isPlaying ? "⏸ Pause Step Tour" : "▶ Auto Play Sequence"}
          </button>

          <button
            className="btn btn-sm"
            onClick={() => {
              setCurrentStep(1);
              setIsPlaying(false);
            }}
            disabled={currentStep <= 1}
            title="First Step"
          >
            |◀ First
          </button>

          <button
            className="btn btn-sm"
            onClick={() => {
              setCurrentStep((prev) => Math.max(1, prev - 1));
              setIsPlaying(false);
            }}
            disabled={currentStep <= 1}
          >
            ◀ Prev
          </button>

          <button
            className="btn btn-sm"
            onClick={() => {
              setCurrentStep((prev) => Math.min(totalSteps, prev + 1));
              setIsPlaying(false);
            }}
            disabled={currentStep >= totalSteps}
          >
            Next ▶
          </button>

          <button
            className="btn btn-sm btn-secondary"
            onClick={() => {
              setCurrentStep(totalSteps);
              setIsPlaying(false);
            }}
            title="Show All Steps At Once"
          >
            Show All ({totalSteps})
          </button>
        </div>
      </div>
    </div>
  );
};
