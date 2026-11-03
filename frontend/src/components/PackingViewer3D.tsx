import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PackingPlan } from "../types/contract";
import { mapPlacementToThreeJSFloor } from "../utils/coordinateTransform";

interface PackingViewer3DProps {
  plan: PackingPlan;
}

type CameraPreset = "iso" | "top" | "front" | "side";

const VIEWPORT_HEIGHT = 400;
const DROP_HEIGHT_MM = 150;
const DROP_DURATION_MS = 380;

export const PackingViewer3D: React.FC<PackingViewer3DProps> = ({ plan }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const itemGroupRef = useRef<THREE.Group | null>(null);

  const [currentStep, setCurrentStep] = useState<number>(plan.placements.length);
  const prevStepRef = useRef<number>(plan.placements.length);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [activePreset, setActivePreset] = useState<CameraPreset>("iso");
  const [showSafetyHalo, setShowSafetyHalo] = useState<boolean>(true);
  const [webGlError, setWebGlError] = useState<string | null>(null);

  const totalSteps = plan.placements.length;

  // Reset step on plan change
  useEffect(() => {
    setCurrentStep(plan.placements.length);
    prevStepRef.current = plan.placements.length;
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

  const setCameraView = (preset: CameraPreset) => {
    setActivePreset(preset);
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;

    const targetY = plan.carton.internal_dimensions_mm.height_mm / 2;
    controls.target.set(0, targetY, 0);
    if (preset === "iso") camera.position.set(380, 320, 480);
    if (preset === "top") camera.position.set(0, 680, 1); // Small Z offset avoids gimbal lock
    if (preset === "front") camera.position.set(0, targetY, 560);
    if (preset === "side") camera.position.set(560, targetY, 0);
    controls.update();
  };

  // Dispose geometries and materials inside a group
  const clearAndDisposeGroup = (group: THREE.Group) => {
    group.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
        obj.geometry?.dispose();
        if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
        else obj.material?.dispose();
      }
    });
    group.clear();
  };

  // Effect 1: Scene, camera, renderer, controls & carton. Re-runs only when the carton changes.
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 600;
    const height = window.innerWidth <= 640 ? 290 : VIEWPORT_HEIGHT;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f5f7);

    const cartonDims = plan.carton.internal_dimensions_mm;
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 3000);
    camera.position.set(380, 320, 480);
    cameraRef.current = camera;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch (err) {
      console.warn("WebGL initialization failed:", err);
      setWebGlError("WebGL context unavailable");
      return;
    }
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI / 2 + 0.12;
    controls.minDistance = 150;
    controls.maxDistance = 1400;
    controls.target.set(0, cartonDims.height_mm / 2, 0);
    controlsRef.current = controls;

    scene.add(new THREE.AmbientLight(0xffffff, 0.9));
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.8);
    keyLight.position.set(250, 450, 300);
    scene.add(keyLight);

    const grid = new THREE.GridHelper(900, 30, 0xd2d2d7, 0xe8e8ed);
    grid.position.y = -1;
    scene.add(grid);

    // Carton outline
    const cartonGeo = new THREE.BoxGeometry(cartonDims.length_mm, cartonDims.height_mm, cartonDims.width_mm);
    const cartonWire = new THREE.LineSegments(
      new THREE.EdgesGeometry(cartonGeo),
      new THREE.LineBasicMaterial({ color: 0x86868b })
    );
    cartonGeo.dispose();
    cartonWire.position.set(0, cartonDims.height_mm / 2, 0);
    scene.add(cartonWire);

    // Carton floor
    const floorGeo = new THREE.PlaneGeometry(cartonDims.length_mm, cartonDims.width_mm);
    floorGeo.rotateX(-Math.PI / 2);
    const floorMesh = new THREE.Mesh(
      floorGeo,
      new THREE.MeshStandardMaterial({ color: 0xe8e8ed, roughness: 0.9 })
    );
    scene.add(floorMesh);

    const itemGroup = new THREE.Group();
    scene.add(itemGroup);
    itemGroupRef.current = itemGroup;

    // Render loop: drop easing + active outline pulse
    let animationFrameId: number;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      controls.update();

      const now = performance.now();
      itemGroupRef.current?.children.forEach((child) => {
        const d = child.userData;
        if (d?.isAnimating) {
          const t = Math.min(1, (now - d.startTime) / d.duration);
          const ease = 1 - (1 - t) * (1 - t); // easeOutQuad
          child.position.y = d.startY + (d.targetY - d.startY) * ease;
          if (t >= 1) {
            child.position.y = d.targetY;
            d.isAnimating = false;
          }
        }
        if (d?.isActive) {
          const outline = child.getObjectByName("activeOutline") as THREE.LineSegments | undefined;
          if (outline && outline.material instanceof THREE.LineBasicMaterial) {
            outline.material.opacity = 0.55 + 0.45 * Math.sin(now * 0.006);
          }
        }
      });

      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!container) return;
      const newWidth = container.clientWidth;
      const newHeight = window.innerWidth <= 640 ? 290 : VIEWPORT_HEIGHT;
      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
      controls.dispose();
      itemGroupRef.current = null;

      // GPU memory cleanup
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
          obj.geometry?.dispose();
          if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
          else obj.material?.dispose();
        }
      });
      renderer.dispose();
      container.innerHTML = "";
    };
  }, [
    plan.carton.carton_id,
    plan.carton.internal_dimensions_mm.length_mm,
    plan.carton.internal_dimensions_mm.width_mm,
    plan.carton.internal_dimensions_mm.height_mm,
  ]);

  // Effect 2: Rebuild item meshes when the step or placements change (camera state is preserved)
  useEffect(() => {
    const itemGroup = itemGroupRef.current;
    if (!itemGroup) return;

    clearAndDisposeGroup(itemGroup);

    const isStepForward = currentStep > prevStepRef.current;
    prevStepRef.current = currentStep;

    plan.placements
      .filter((p) => p.step_number <= currentStep)
      .forEach((p) => {
        const { size, position } = mapPlacementToThreeJSFloor(plan.carton, p);
        const [wPlaced, hPlaced, dPlaced] = size; // placed dimensions incl. safety margin
        const [x, y, z] = position;
        const isActive = p.step_number === currentStep;

        const group = new THREE.Group();
        const animateDrop = isActive && isStepForward;
        const startY = Math.max(plan.carton.internal_dimensions_mm.height_mm + DROP_HEIGHT_MM, y + DROP_HEIGHT_MM);
        group.position.set(x, animateDrop ? startY : y, z);
        group.userData = {
          targetY: y,
          startY,
          startTime: performance.now(),
          duration: DROP_DURATION_MS,
          isAnimating: animateDrop,
          isActive,
        };

        // Halo ON: nominal box + margin envelope. Halo OFF: solid box at placed dims.
        const nom = p.nominal_dimensions_mm || p.placed_dimensions_mm;
        const solidGeo = showSafetyHalo
          ? new THREE.BoxGeometry(Math.min(nom.dx, wPlaced), Math.min(nom.dz, hPlaced), Math.min(nom.dy, dPlaced))
          : new THREE.BoxGeometry(wPlaced, hPlaced, dPlaced);
        const solid = new THREE.Mesh(
          solidGeo,
          new THREE.MeshStandardMaterial({
            color: new THREE.Color(p.display_color_hex || "#0071e3"),
            roughness: 0.55,
            transparent: !isActive && currentStep < totalSteps,
            opacity: !isActive && currentStep < totalSteps ? 0.7 : 1,
          })
        );
        solid.add(
          new THREE.LineSegments(
            new THREE.EdgesGeometry(solidGeo),
            new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6 })
          )
        );
        group.add(solid);

        // Safety margin envelope (subtle)
        const haloGeo = new THREE.BoxGeometry(wPlaced, hPlaced, dPlaced);
        const haloEdges = new THREE.EdgesGeometry(haloGeo);
        haloGeo.dispose();
        if (showSafetyHalo) {
          group.add(
            new THREE.LineSegments(
              haloEdges.clone(),
              new THREE.LineBasicMaterial({ color: 0x86868b, transparent: true, opacity: 0.35 })
            )
          );
        }

        // Active step outline
        if (isActive) {
          const outline = new THREE.LineSegments(
            haloEdges.clone(),
            new THREE.LineBasicMaterial({ color: 0x0071e3, transparent: true, opacity: 1 })
          );
          outline.name = "activeOutline";
          group.add(outline);
        }
        haloEdges.dispose();

        itemGroup.add(group);
      });
  }, [plan.carton, plan.placements, currentStep, totalSteps, showSafetyHalo]);

  const activeItem = plan.placements.find((p) => p.step_number === currentStep);

  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
      return;
    }
    if (currentStep >= totalSteps) {
      prevStepRef.current = 0;
      setCurrentStep(1);
    }
    setIsPlaying(true);
  };

  return (
    <section className="panel panel-flush">
      <header className="panel-head padded">
        <h2>
          Packing <span className="muted">{plan.carton.display_name || plan.carton.carton_id}</span>
        </h2>
        <div className="head-actions">
        <label className="check" title="Show the measurement safety margin around each item">
          <input
            type="checkbox"
            checked={showSafetyHalo}
            onChange={(e) => setShowSafetyHalo(e.target.checked)}
          />
          Margin
        </label>
        <div className="segmented">
          {(["iso", "top", "front", "side"] as CameraPreset[]).map((p) => (
            <button
              key={p}
              type="button"
              className={activePreset === p ? "is-active" : ""}
              onClick={() => setCameraView(p)}
            >
              {{ iso: "3D", top: "Top", front: "Front", side: "Side" }[p]}
            </button>
          ))}
        </div>
        </div>
      </header>

      <div className="viewport" ref={mountRef}>
        {webGlError && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--muted)", gap: 6, textAlign: "center", padding: 16 }}>
            <span style={{ fontSize: 24 }}>📦</span>
            <strong style={{ fontSize: 13, color: "var(--text)" }}>3D Simulation Paused</strong>
            <span style={{ fontSize: 11 }}>Hardware acceleration or WebGL is disabled in this environment.</span>
          </div>
        )}
      </div>

      <div className="player">
        <button
          type="button"
          className="play-btn"
          onClick={togglePlay}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          min={1}
          max={totalSteps}
          value={currentStep}
          onChange={(e) => {
            setCurrentStep(parseInt(e.target.value, 10) || 1);
            setIsPlaying(false);
          }}
          className="slider"
        />
        <span className="player-step">
          {currentStep}/{totalSteps}
        </span>
      </div>
      {activeItem && (
        <p className="player-caption">
          <span className="dot" style={{ backgroundColor: activeItem.display_color_hex }} />
          {activeItem.display_name}
          <span className="muted"> · {activeItem.rotation_code}</span>
        </p>
      )}
    </section>
  );
};
