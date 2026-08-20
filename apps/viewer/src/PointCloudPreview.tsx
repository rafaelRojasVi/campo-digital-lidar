import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { PLYLoader } from 'three/addons/loaders/PLYLoader.js'
import { artifactUrl } from './api'
import './PointCloudPreview.css'

interface PreviewManifest {
  schema_version: string
  kind: string
  ply_path: string
  source_point_count: number
  preview_point_count: number
  sampling: {
    method: string
    max_points: number
    seed: number
  }
  coordinate_units: string
  coordinate_space: string
  position_encoding: string
  ply_encoding: string
  origin_source_coordinates: [number, number, number]
  source_bounds: {
    min: [number, number, number]
    max: [number, number, number]
  }
  preview_local_bounds: {
    min: [number, number, number]
    max: [number, number, number]
  }
  measurement_frame: {
    center_xy_source: [number, number]
    longitudinal_axis_xy: [number, number]
    transverse_axis_xy: [number, number]
  }
}

interface PointCloudPreviewProps {
  runId: string
  plyPath: string
  manifestPath: string
}

type ViewerState =
  | { status: 'loading' }
  | { status: 'ready'; manifest: PreviewManifest }
  | { status: 'error'; message: string }

function loadManifest(
  runId: string,
  manifestPath: string,
): Promise<PreviewManifest> {
  return fetch(artifactUrl(runId, manifestPath)).then(async (response) => {
    if (!response.ok) {
      throw new Error(
        `Preview manifest request failed: ${response.status} ${response.statusText}`,
      )
    }

    return (await response.json()) as PreviewManifest
  })
}

function disposeMaterial(
  material: THREE.Material | THREE.Material[],
): void {
  if (Array.isArray(material)) {
    material.forEach((item) => item.dispose())
    return
  }

  material.dispose()
}

function makeMeasurementAxis(
  center: THREE.Vector3,
  direction: THREE.Vector3,
  length: number,
  color: number,
): THREE.Line {
  const half = direction.clone().normalize().multiplyScalar(length / 2)

  const geometry = new THREE.BufferGeometry().setFromPoints([
    center.clone().sub(half),
    center.clone().add(half),
  ])

  const material = new THREE.LineBasicMaterial({ color })

  return new THREE.Line(geometry, material)
}

export default function PointCloudPreview({
  runId,
  plyPath,
  manifestPath,
}: PointCloudPreviewProps) {
  const mountRef = useRef<HTMLDivElement | null>(null)
  const [viewerState, setViewerState] = useState<ViewerState>({
    status: 'loading',
  })

  useEffect(() => {
    const mount = mountRef.current

    if (!mount) {
      return
    }

    let cancelled = false
    let animationFrame = 0

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x101713)

    const camera = new THREE.PerspectiveCamera(48, 1, 0.01, 1000)
    camera.up.set(0, 0, 1)

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
    })

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace

    mount.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08

    const loader = new PLYLoader()

    const resize = () => {
      const width = Math.max(mount.clientWidth, 1)
      const height = Math.max(mount.clientHeight, 1)

      renderer.setSize(width, height, false)

      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(mount)
    resize()

    async function initialise() {
      try {
        const [manifest, geometry] = await Promise.all([
          loadManifest(runId, manifestPath),
          loader.loadAsync(artifactUrl(runId, plyPath)),
        ])

        if (cancelled) {
          geometry.dispose()
          return
        }

        geometry.computeBoundingBox()

        const boundingBox = geometry.boundingBox

        if (!boundingBox) {
          geometry.dispose()
          throw new Error('Point-cloud preview has no bounding box')
        }

        const position = geometry.getAttribute('position')

        if (!position || position.count === 0) {
          geometry.dispose()
          throw new Error('Point-cloud preview contains no vertices')
        }

        const material = new THREE.PointsMaterial({
          color: 0xd8f3df,
          size: 0.055,
          sizeAttenuation: true,
        })

        const points = new THREE.Points(geometry, material)
        scene.add(points)

        const center = new THREE.Vector3()
        const size = new THREE.Vector3()

        boundingBox.getCenter(center)
        boundingBox.getSize(size)

        const extent = Math.max(size.x, size.y, size.z, 1)

        const boxHelper = new THREE.Box3Helper(
          boundingBox,
          new THREE.Color(0x60786a),
        )
        scene.add(boxHelper)

        const origin = manifest.origin_source_coordinates
        const frameCenter = manifest.measurement_frame.center_xy_source

        const measurementCenter = new THREE.Vector3(
          frameCenter[0] - origin[0],
          frameCenter[1] - origin[1],
          center.z,
        )

        const longitudinal = new THREE.Vector3(
          manifest.measurement_frame.longitudinal_axis_xy[0],
          manifest.measurement_frame.longitudinal_axis_xy[1],
          0,
        )

        const transverse = new THREE.Vector3(
          manifest.measurement_frame.transverse_axis_xy[0],
          manifest.measurement_frame.transverse_axis_xy[1],
          0,
        )

        const axisLength = extent * 0.28

        const longitudinalAxis = makeMeasurementAxis(
          measurementCenter,
          longitudinal,
          axisLength,
          0xf3b562,
        )

        const transverseAxis = makeMeasurementAxis(
          measurementCenter,
          transverse,
          axisLength,
          0x62b6f3,
        )

        const verticalAxis = makeMeasurementAxis(
          measurementCenter,
          new THREE.Vector3(0, 0, 1),
          Math.max(size.z, extent * 0.12),
          0xe76f8a,
        )

        scene.add(longitudinalAxis, transverseAxis, verticalAxis)

        const frontDistance = extent * 1.25
        const elevation = extent * 0.18

        camera.position.set(
          measurementCenter.x - transverse.x * frontDistance,
          measurementCenter.y - transverse.y * frontDistance,
          measurementCenter.z + elevation,
        )

        camera.near = Math.max(extent / 10_000, 0.001)
        camera.far = extent * 20
        camera.updateProjectionMatrix()

        controls.target.copy(measurementCenter)
        controls.minDistance = extent * 0.08
        controls.maxDistance = extent * 6
        controls.update()
        controls.saveState()

        setViewerState({
          status: 'ready',
          manifest,
        })
      } catch (reason) {
        if (!cancelled) {
          setViewerState({
            status: 'error',
            message: reason instanceof Error ? reason.message : String(reason),
          })
        }
      }
    }

    void initialise()

    const animate = () => {
      controls.update()
      renderer.render(scene, camera)
      animationFrame = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      cancelled = true
      cancelAnimationFrame(animationFrame)

      resizeObserver.disconnect()
      controls.dispose()

      scene.traverse((object) => {
        if (object instanceof THREE.Points || object instanceof THREE.Line) {
          object.geometry.dispose()
          disposeMaterial(object.material)
        }

        if (object instanceof THREE.Box3Helper) {
          object.geometry.dispose()
          disposeMaterial(object.material)
        }
      })

      renderer.dispose()

      if (renderer.domElement.parentElement === mount) {
        mount.removeChild(renderer.domElement)
      }
    }
  }, [runId, plyPath, manifestPath])

  return (
    <div className="point-cloud-preview">
      <div className="point-cloud-stage" ref={mountRef} />

      <div className="point-cloud-overlay">
        {viewerState.status === 'loading' && <span>Loading 3D preview…</span>}

        {viewerState.status === 'error' && (
          <span className="point-cloud-error">{viewerState.message}</span>
        )}

        {viewerState.status === 'ready' && (
          <>
            <span>
              {viewerState.manifest.preview_point_count.toLocaleString()} preview
              points
            </span>
            <span>
              from{' '}
              {viewerState.manifest.source_point_count.toLocaleString()} selected
              points
            </span>
            <span>{viewerState.manifest.coordinate_units}</span>
          </>
        )}
      </div>

      <div className="point-cloud-help">
        Drag to orbit · wheel to zoom · right-drag to pan
      </div>
    </div>
  )
}
