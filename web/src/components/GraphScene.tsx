import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
export interface MapNode {
  id: string;
  type: string;
  title?: string;
  label?: string;
  lifecycle?: string;
  issued?: string;
  in_force_from?: string;
  in_force_to?: string;
  document_id?: string;
  x?: number;
  y?: number;
  community?: number;
  degree: number;
}
export interface MapEdge {
  source: string;
  target: string;
  type: string;
  trust?: string;
}
export const COLORS: Record<string, string> = {
  Document: "#bee895",
  Provision: "#70c6b1",
  DefinedTerm: "#c5acf4",
  Authority: "#e9cf88",
  RegulatedEntity: "#8bbbea",
  Product: "#f4ad8e",
};
interface Props {
  nodes: MapNode[];
  edges: MapEdge[];
  selected: string | null;
  day: string;
  flat: boolean;
  onSelect: (id: string) => void;
}
type SceneHandle = {
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  render: () => void;
  reset: () => void;
  positions: Map<string, THREE.Vector3>;
  selection: THREE.Mesh;
};
export default function GraphScene({
  nodes,
  edges,
  selected,
  day,
  flat,
  onSelect,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const handle = useRef<SceneHandle | null>(null);
  const choose = useRef(onSelect);
  choose.current = onSelect;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [failure, setFailure] = useState(false);
  const [hover, setHover] = useState("");
  useEffect(() => {
    if (!host.current || !nodes.length) return;
    const element = host.current;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: "low-power",
      });
    } catch {
      setFailure(true);
      return;
    }
    setFailure(false);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor("#0c211c");
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(46, 1, 0.1, 5000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.enableRotate = !flat;
    controls.minDistance = 30;
    controls.maxDistance = 1900;
    controls.zoomSpeed = 0.8;
    controls.panSpeed = 0.7;
    const positions = new Map<string, THREE.Vector3>();
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const xs = nodes.map((n) => n.x ?? 0),
      ys = nodes.map((n) => n.y ?? 0);
    const minX = Math.min(...xs),
      maxX = Math.max(...xs),
      minY = Math.min(...ys),
      maxY = Math.max(...ys);
    const scale = 400 / Math.max(maxX - minX, maxY - minY, 1);
    nodes.forEach((n, i) => {
      let hash = 0;
      for (const c of n.id) hash = (hash * 31 + c.charCodeAt(0)) | 0;
      const z = flat ? 0 : ((Math.abs(hash) % 151) - 75) * 1.7;
      const x = ((n.x ?? Math.cos(i) * 100) - (minX + maxX) / 2) * scale;
      const y = ((n.y ?? Math.sin(i) * 100) - (minY + maxY) / 2) * scale;
      positions.set(n.id, new THREE.Vector3(x, y, z));
    });
    const sphere = new THREE.SphereGeometry(1, 12, 8);
    const material = new THREE.MeshBasicMaterial();
    const mesh = new THREE.InstancedMesh(sphere, material, nodes.length);
    const dummy = new THREE.Object3D();
    nodes.forEach((n, i) => {
      dummy.position.copy(positions.get(n.id)!);
      const size =
        n.type === "Document" ? 4.8 : n.type === "Provision" ? 1.6 : 3.2;
      dummy.scale.setScalar(size);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      const doc = n.type === "Document" ? n : byId.get(n.document_id ?? "");
      const expired = doc?.in_force_to && doc.in_force_to <= day;
      mesh.setColorAt(
        i,
        new THREE.Color(expired ? "#b87879" : (COLORS[n.type] ?? "#b8c9b9")),
      );
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    scene.add(mesh);
    const vertices: number[] = [],
      colors: number[] = [];
    edges.forEach((edge) => {
      const a = positions.get(edge.source),
        b = positions.get(edge.target);
      if (!a || !b) return;
      vertices.push(a.x, a.y, a.z, b.x, b.y, b.z);
      const color = new THREE.Color(
        ["SUPERSEDES", "WITHDRAWS"].includes(edge.type) ? "#b67876" : "#456f5b",
      );
      colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
    });
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(vertices, 3),
    );
    lineGeo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: nodes.length > 500 ? 0.2 : 0.5,
      depthWrite: false,
    });
    scene.add(new THREE.LineSegments(lineGeo, lineMat));
    const selectGeo = new THREE.SphereGeometry(7, 16, 12);
    const selectMat = new THREE.MeshBasicMaterial({
      color: "#f0f7cc",
      wireframe: true,
      transparent: true,
      opacity: 0.8,
    });
    const selection = new THREE.Mesh(selectGeo, selectMat);
    selection.visible = false;
    scene.add(selection);
    const render = () => {
      renderer.render(scene, camera);
    };
    const reset = () => {
      controls.target.set(0, 0, 0);
      camera.position.set(flat ? 0 : 100, flat ? 0 : 100, 620);
      controls.update();
      render();
    };
    handle.current = { camera, controls, render, reset, positions, selection };
    reset();
    const current = positions.get(selectedRef.current ?? "");
    if (current) {
      selection.position.copy(current);
      selection.visible = true;
    }
    const resize = () => {
      const width = element.clientWidth,
        height = element.clientHeight;
      if (width === 0 || height === 0) return;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    controls.addEventListener("change", render);
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let down: { x: number; y: number } | null = null;
    const pick = (e: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        (-(e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObject(mesh)[0];
      return hit?.instanceId === undefined ? undefined : nodes[hit.instanceId];
    };
    const onDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY };
    };
    const onUp = (e: PointerEvent) => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 5) {
        const node = pick(e);
        if (node) choose.current(node.id);
      }
      down = null;
    };
    const move = (e: PointerEvent) => {
      if (e.buttons) return;
      const n = pick(e);
      setHover(n ? `${n.type}: ${n.title ?? n.label ?? n.id}` : "");
      renderer.domElement.style.cursor = n ? "pointer" : "grab";
    };
    const leave = () => setHover("");
    const lost = (e: Event) => {
      e.preventDefault();
      setFailure(true);
    };
    renderer.domElement.addEventListener("webglcontextlost", lost);
    element.addEventListener("pointerdown", onDown);
    element.addEventListener("pointerup", onUp);
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerleave", leave);
    return () => {
      observer.disconnect();
      controls.removeEventListener("change", render);
      controls.dispose();
      element.removeEventListener("pointerdown", onDown);
      element.removeEventListener("pointerup", onUp);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerleave", leave);
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      sphere.dispose();
      material.dispose();
      mesh.dispose();
      lineGeo.dispose();
      lineMat.dispose();
      selectGeo.dispose();
      selectMat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      handle.current = null;
    };
  }, [nodes, edges, day, flat]);
  useEffect(() => {
    const h = handle.current;
    if (!h) return;
    const p = h.positions.get(selected ?? "");
    h.selection.visible = Boolean(p);
    if (p) {
      h.selection.position.copy(p);
      const offset = h.camera.position.clone().sub(h.controls.target);
      h.controls.target.copy(p);
      h.camera.position.copy(p).add(offset);
      h.controls.update();
    }
    h.render();
  }, [selected, nodes]);
  const zoom = (factor: number) => {
    const h = handle.current;
    if (h) {
      const offset = h.camera.position
        .clone()
        .sub(h.controls.target)
        .multiplyScalar(factor);
      h.camera.position.copy(h.controls.target).add(offset);
      h.controls.update();
      h.render();
    }
  };
  const rotate = (angle: number) => {
    const h = handle.current;
    if (h && !flat) {
      h.camera.position
        .sub(h.controls.target)
        .applyAxisAngle(new THREE.Vector3(0, 1, 0), angle)
        .add(h.controls.target);
      h.controls.update();
      h.render();
    }
  };
  return (
    <div className="graph-stage">
      <div
        ref={host}
        className="graph-canvas"
        tabIndex={0}
        role="group"
        aria-label="Interactive graph. Left and right arrows rotate in 3D. Plus and minus zoom. Home resets. Use document search or list to select nodes."
        onKeyDown={(e) => {
          if (
            ["ArrowLeft", "ArrowRight", "+", "=", "-", "Home"].includes(e.key)
          ) {
            e.preventDefault();
            if (e.key === "Home") handle.current?.reset();
            else if (e.key === "ArrowLeft") rotate(-0.2);
            else if (e.key === "ArrowRight") rotate(0.2);
            else zoom(e.key === "-" ? 1.2 : 0.8);
          }
        }}
      />
      <div className="graph-overlay-top">
        <span>
          {flat ? "2D MAP" : "3D EXPLORER"} · {nodes.length.toLocaleString()}{" "}
          nodes in this view
        </span>
        <span>Drag to {flat ? "pan" : "orbit"} · scroll to zoom</span>
      </div>
      {hover && !failure && <div className="graph-tooltip">{hover}</div>}
      {failure && (
        <div className="graph-fallback">
          <h3>3D rendering is unavailable here.</h3>
          <p>
            Search and the document list below still work. You can inspect every
            available node’s text and relationships without the canvas.
          </p>
        </div>
      )}
      <div className="graph-controls" aria-label="Camera controls">
        <button aria-label="Zoom in" onClick={() => zoom(0.8)}>
          +
        </button>
        <button aria-label="Zoom out" onClick={() => zoom(1.2)}>
          −
        </button>
        <button
          aria-label="Rotate left"
          disabled={flat}
          onClick={() => rotate(-0.3)}
        >
          ↶
        </button>
        <button
          aria-label="Rotate right"
          disabled={flat}
          onClick={() => rotate(0.3)}
        >
          ↷
        </button>
        <button onClick={() => handle.current?.reset()}>Reset view</button>
      </div>
    </div>
  );
}
