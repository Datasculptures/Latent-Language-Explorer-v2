import * as THREE from 'three'
import type { SurfaceMode } from '../types'
import { useAppStore } from '../store'

/**
 * SceneManager -- singleton owner of the Three.js renderer.
 *
 * Lifecycle:
 *   1. App.tsx calls SceneManager.getInstance().init(canvas)
 *   2. Data is loaded and passed to SceneManager via loadTerrain() / loadConcepts()
 *   3. Both Landscape and Discovery pages call SceneManager methods for
 *      navigation, filtering, and discovery operations.
 *   4. The canvas is never removed from the DOM.
 *
 * Coordinate systems (from ARCHITECTURE.md):
 *   - position_2d [x, y]: 2D UMAP layout coordinates
 *   - scene position [x, height, -y]: Three.js scene coordinates
 *     x = umap_x, height = density lookup, z = -umap_y (y-flip for Three.js)
 *   - The y-flip is necessary because UMAP y increases upward but Three.js
 *     z increases toward the viewer.
 */
export class SceneManager {
  private static _instance: SceneManager | null = null

  // Three.js core
  renderer!:  THREE.WebGLRenderer
  scene!:     THREE.Scene
  camera!:    THREE.PerspectiveCamera
  private _animFrameId: number = 0
  private _canvas: HTMLCanvasElement | null = null
  private _initialized = false

  // Scene objects (populated after data load)
  private _terrainMesh:     THREE.Mesh | null = null
  private _conceptSpheres:  THREE.InstancedMesh | null = null
  private _basinFill:       THREE.Mesh | null = null
  private _basinBoundaries: THREE.LineSegments | null = null
  private _attractorGroup:  THREE.Group | null = null
  private _probeGroup:      THREE.Group | null = null
  private _journalGroup:    THREE.Group | null = null
  private _deepestMarker:   THREE.Mesh | null = null

  // Voronoi
  private _voronoiMesh: THREE.InstancedMesh | null = null
  private _voronoiData: any[] = []

  // Atmosphere layer (context variant spheres, filaments, hulls)
  private _atmosphereOn    = false
  private _atmSpheres:    THREE.InstancedMesh  | null = null
  private _atmFilaments:  THREE.LineSegments   | null = null
  private _atmHullGroup:  THREE.Group          | null = null
  // Per-instance lookup: instanceId → { conceptIndex, contextIndex }
  private _variantMeta: Array<{ conceptIndex: number; contextIndex: number }> = []

  // Atmosphere rendering constants (mirrors terrain_config.py)
  private readonly _ATM_MIN_POLYSEMY  = 0.3
  private readonly _ATM_HULL_POLYSEMY = 0.7
  private readonly _ATM_MAX_VARIANTS  = 50000
  private readonly _ATM_MAX_HULLS     = 200
  private readonly _CONTEXT_KEYS = [
    'abstract_relations','space','matter','intellect','volition','affections','neutral',
  ]

  // Concept path
  private _pathGroup:         THREE.Group | null = null
  private _pathWaypoints:     THREE.Vector3[] = []
  private _pathWaypointIndex: number = 0

  // Surface mode
  private _currentSurfaceMode: SurfaceMode = 'density'
  private _attractorMeshes: THREE.Mesh[] = []

  // Concept sphere tracking
  private _conceptPositions: THREE.Vector3[] = []
  private _rogetClassId: number | null = null

  // Tortuosity colour mode
  private _tortuosityMode = false

  // Terrain data
  private _terrainData:  any    = null
  private _conceptData:  any[]  = []
  private _densityGrid:  number[][] = []
  private _xGrid:        number[]   = []
  private _yGrid:        number[]   = []

  // Navigation
  private _keys:       Record<string, boolean> = {}
  private _moveSpeed   = 0.05
  private _yaw         = 0
  private _pitch       = 0
  private _isDragging  = false
  private _lastMouseX  = 0
  private _lastMouseY  = 0

  // Ground following
  private readonly _EYE_HEIGHT          = 1.2
  private readonly _LERP_SPEED          = 0.12
  private readonly _GROUND_OVERRIDE_MS  = 2000
  private _groundFollow         = true
  private _groundFollowOverride = false
  private _groundFollowOverrideTime = 0
  private _flyingTo             = false

  static getInstance(): SceneManager {
    if (!SceneManager._instance) {
      SceneManager._instance = new SceneManager()
    }
    return SceneManager._instance
  }

  init(canvas: HTMLCanvasElement): void {
    if (this._initialized) return
    this._canvas = canvas

    // Renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
    })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setSize(canvas.clientWidth, canvas.clientHeight)
    this.renderer.setClearColor(0x0a0a0f)

    // Scene
    this.scene = new THREE.Scene()
    this.scene.fog = new THREE.FogExp2(0x0a0a0f, 0.015)

    // Camera
    this.camera = new THREE.PerspectiveCamera(
      60,
      canvas.clientWidth / canvas.clientHeight,
      0.01,
      200,
    )
    this.camera.position.set(0, 8, 12)
    this.camera.lookAt(0, 0, 0)

    // Lighting
    const ambient  = new THREE.AmbientLight(0xffffff, 0.4)
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8)
    dirLight.position.set(5, 10, 5)
    this.scene.add(ambient, dirLight)

    // Journal group — persistent across data reloads
    this._journalGroup = new THREE.Group()
    this.scene.add(this._journalGroup)

    // Input
    this._bindInput()

    // Resize observer
    const ro = new ResizeObserver(() => this._onResize())
    ro.observe(canvas)

    // Animation loop
    this._loop()
    this._initialized = true
  }

  // ── Coordinate conversion ──────────────────────────────────────────────────

  /**
   * Convert 2D UMAP position to Three.js scene position.
   * y-flip: UMAP y+ is up, Three.js z+ is toward viewer.
   */
  umapToScene(umapX: number, umapY: number): THREE.Vector3 {
    const height = this._sampleDensity(umapX, umapY) * 3.0  // scale factor
    return new THREE.Vector3(umapX, height, -umapY)
  }

  private _sampleDensity(ux: number, uy: number): number {
    if (!this._xGrid.length || !this._yGrid.length) return 0
    const gx  = this._xGrid
    const gy  = this._yGrid
    const res = gx.length

    let ci = gx.findIndex(x => x > ux) - 1
    let ri = gy.findIndex(y => y > uy) - 1
    ci = Math.max(0, Math.min(ci, res - 2))
    ri = Math.max(0, Math.min(ri, res - 2))

    const tx  = (ux - gx[ci]) / (gx[ci + 1] - gx[ci] + 1e-8)
    const ty  = (uy - gy[ri]) / (gy[ri + 1] - gy[ri] + 1e-8)
    const tx_ = Math.max(0, Math.min(tx, 1))
    const ty_ = Math.max(0, Math.min(ty, 1))

    const d = this._densityGrid
    if (!d[ri] || !d[ri + 1]) return 0
    const v00 = d[ri][ci]       ?? 0
    const v10 = d[ri][ci + 1]   ?? 0
    const v01 = d[ri + 1][ci]   ?? 0
    const v11 = d[ri + 1][ci + 1] ?? 0

    return v00 * (1-tx_)*(1-ty_) + v10 * tx_*(1-ty_) +
           v01 * (1-tx_)*ty_     + v11 * tx_*ty_
  }

  /**
   * Return the scene-space Y value of the terrain surface at the given
   * scene-space (x, z) position, using bilinear interpolation.
   * Returns 0 if the grid has not been loaded or the point is out of bounds.
   */
  getTerrainHeightAt(x: number, z: number): number {
    if (!this._xGrid.length || !this._yGrid.length) return 0
    // Reverse the coordinate transform: scene x = umap_x, scene z = -umap_y
    const umapX = x
    const umapY = -z
    const gx = this._xGrid
    const gy = this._yGrid
    // Out-of-bounds check
    if (umapX < gx[0] || umapX > gx[gx.length - 1] ||
        umapY < gy[0] || umapY > gy[gy.length - 1]) return 0
    return this._sampleDensity(umapX, umapY) * 3.0  // HEIGHT_SCALE = 3.0
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  loadTerrain(terrainData: any): void {
    this._terrainData = terrainData
    this._densityGrid = terrainData.density
    this._xGrid       = terrainData.x_grid
    this._yGrid       = terrainData.y_grid
    this._buildTerrainMesh()
    this._buildBasins()
    this._buildAttractors()
  }

  loadConcepts(concepts: any[]): void {
    this._conceptData = concepts
    this._buildConceptSpheres()
  }

  // ── Animation loop ─────────────────────────────────────────────────────────

  private _loop(): void {
    this._animFrameId = requestAnimationFrame(() => this._loop())
    this._updateCamera()
    this._animateAttractors()
    this._animateDeepestMarker()
    this.renderer.render(this.scene, this.camera)
  }

  // ── Navigation ─────────────────────────────────────────────────────────────

  private _bindInput(): void {
    const SURFACE_MODES: SurfaceMode[] = ['wireframe', 'density', 'contour', 'desert']

    window.addEventListener('keydown', e => {
      this._keys[e.code] = true

      if (e.code === 'KeyT') {
        const idx  = SURFACE_MODES.indexOf(this._currentSurfaceMode)
        const next = SURFACE_MODES[(idx + 1) % SURFACE_MODES.length]
        this.setSurfaceMode(next)
        useAppStore.getState().setSurfaceMode(next)
      }

      if (e.code === 'KeyQ' || e.code === 'KeyE') {
        this._groundFollowOverride     = true
        this._groundFollowOverrideTime = performance.now()
      }

      if (e.code === 'KeyN') this.stepConceptPath(1)
      if (e.code === 'KeyP') this.stepConceptPath(-1)
      if (e.code === 'Escape') this.clearConceptPath()

      // Shift+A — toggle atmosphere layer (matches V1 keybind)
      if (e.code === 'KeyA' && e.shiftKey) {
        const next = !this._atmosphereOn
        this.setAtmosphere(next)
        useAppStore.getState().setAtmosphereOn(next)
      }
    })
    window.addEventListener('keyup', e => { this._keys[e.code] = false })

    this._canvas!.addEventListener('mousedown', e => {
      if (e.button === 2) {
        this._isDragging = true
        this._lastMouseX = e.clientX
        this._lastMouseY = e.clientY
      }
    })
    window.addEventListener('mouseup',   () => { this._isDragging = false })
    window.addEventListener('mousemove', e => {
      if (!this._isDragging) return
      const dx = e.clientX - this._lastMouseX
      const dy = e.clientY - this._lastMouseY
      this._yaw   -= dx * 0.003
      this._pitch -= dy * 0.003
      this._pitch  = Math.max(-Math.PI/3, Math.min(Math.PI/3, this._pitch))
      this._lastMouseX = e.clientX
      this._lastMouseY = e.clientY
    })

    this._canvas!.addEventListener('wheel', e => {
      const dir = new THREE.Vector3()
      this.camera.getWorldDirection(dir)
      this.camera.position.addScaledVector(dir, -e.deltaY * 0.01)
    }, { passive: true })

    this._canvas!.addEventListener('contextmenu', e => e.preventDefault())
  }

  private _updateCamera(): void {
    const speed = this._moveSpeed
    const dir   = new THREE.Vector3()
    this.camera.getWorldDirection(dir)
    const right = new THREE.Vector3()
    right.crossVectors(dir, new THREE.Vector3(0, 1, 0)).normalize()

    const isMoving =
      this._keys['KeyW']     || this._keys['ArrowUp']    ||
      this._keys['KeyS']     || this._keys['ArrowDown']  ||
      this._keys['ArrowLeft']|| this._keys['ArrowRight']

    if (this._keys['KeyW'] || this._keys['ArrowUp'])    this.camera.position.addScaledVector(dir, speed)
    if (this._keys['KeyS'] || this._keys['ArrowDown'])  this.camera.position.addScaledVector(dir, -speed)
    if (this._keys['ArrowLeft'])                        this.camera.position.addScaledVector(right, -speed)
    if (this._keys['ArrowRight'])                       this.camera.position.addScaledVector(right, speed)
    if (this._keys['KeyA'])                             this._yaw += 0.02
    if (this._keys['KeyD'])                             this._yaw -= 0.02
    if (this._keys['KeyQ'])                             this.camera.position.y += speed
    if (this._keys['KeyE'])                             this.camera.position.y -= speed

    const qYaw   = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0), this._yaw)
    const qPitch = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0), this._pitch)
    this.camera.quaternion.copy(qYaw).multiply(qPitch)

    if (this._keys['KeyH']) {
      this.camera.position.set(0, 8, 12)
      this._yaw = 0
      this._pitch = 0
      this._groundFollowOverride = false
    }

    // Re-engage ground following after Q/E override timeout
    if (this._groundFollowOverride &&
        (performance.now() - this._groundFollowOverrideTime > this._GROUND_OVERRIDE_MS)) {
      this._groundFollowOverride = false
    }

    // Ground following
    if (this._groundFollow && !this._groundFollowOverride && !this._flyingTo) {
      const groundY = this.getTerrainHeightAt(
        this.camera.position.x,
        this.camera.position.z,
      )
      if (groundY !== 0 && !isNaN(groundY)) {
        const targetY = groundY + this._EYE_HEIGHT
        // If the camera is significantly above the target and the player isn't
        // moving, hold position — engage the lerp only once they move.
        const tooHigh = this.camera.position.y > targetY + 2.0 && !isMoving
        if (!tooHigh) {
          this.camera.position.y = THREE.MathUtils.lerp(
            this.camera.position.y, targetY, this._LERP_SPEED,
          )
          // Hard floor — never clip into the terrain
          if (this.camera.position.y < groundY) this.camera.position.y = groundY
        }
      }
    }
  }

  flyTo(scenePos: THREE.Vector3, duration = 1200): void {
    this._flyingTo = true
    const start     = this.camera.position.clone()
    const target    = scenePos.clone().add(new THREE.Vector3(0, 3, 3))
    const startTime = performance.now()
    const animate   = () => {
      const t    = Math.min((performance.now() - startTime) / duration, 1)
      const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t
      this.camera.position.lerpVectors(start, target, ease)
      this.camera.lookAt(scenePos)
      if (t < 1) {
        requestAnimationFrame(animate)
      } else {
        // Re-engage ground following 500 ms after the fly-to completes
        setTimeout(() => { this._flyingTo = false }, 500)
      }
    }
    animate()
  }

  // ── Resize ─────────────────────────────────────────────────────────────────

  private _onResize(): void {
    if (!this._canvas) return
    const w = this._canvas.clientWidth
    const h = this._canvas.clientHeight
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  // ── Build terrain mesh ─────────────────────────────────────────────────────

  private _buildTerrainMesh(): void {
    if (this._terrainMesh) {
      this.scene.remove(this._terrainMesh)
      ;(this._terrainMesh.material as THREE.Material).dispose()
      this._terrainMesh.geometry.dispose()
      this._terrainMesh = null
    }

    const density = this._densityGrid
    const xGrid   = this._xGrid
    const yGrid   = this._yGrid
    const res     = xGrid.length  // 128

    const W   = xGrid[res-1] - xGrid[0]
    const H   = yGrid[res-1] - yGrid[0]
    const geo = new THREE.PlaneGeometry(W, H, res-1, res-1)
    geo.rotateX(-Math.PI / 2)

    // PlaneGeometry row ri corresponds to umap_y = yGrid[res-1-ri]
    // (top row ri=0 has largest y; bottom row ri=res-1 has smallest y)
    const HEIGHT_SCALE = 3.0
    const pos = geo.attributes.position as THREE.BufferAttribute
    const col = new Float32Array(pos.count * 3)

    for (let ri = 0; ri < res; ri++) {
      const dRow = res - 1 - ri  // density row index for this geometry row
      for (let ci = 0; ci < res; ci++) {
        const idx = ri * res + ci
        const d   = density[dRow]?.[ci] ?? 0
        pos.setY(idx, d * HEIGHT_SCALE)
        col[idx*3+0] = 0.05 + d * 0.10
        col[idx*3+1] = 0.15 + d * 0.35
        col[idx*3+2] = 0.25 + d * 0.45
      }
    }

    pos.needsUpdate = true
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
    geo.computeVertexNormals()

    const mat = new THREE.MeshLambertMaterial({ vertexColors: true, wireframe: false })
    this._terrainMesh = new THREE.Mesh(geo, mat)
    this._terrainMesh.position.set(
      (xGrid[0] + xGrid[res-1]) / 2,
      0,
      -(yGrid[0] + yGrid[res-1]) / 2,
    )
    this.scene.add(this._terrainMesh)
    this._currentSurfaceMode = 'density'
  }

  // ── Surface mode ───────────────────────────────────────────────────────────

  setSurfaceMode(mode: SurfaceMode): void {
    this._currentSurfaceMode = mode
    if (!this._terrainMesh) return
    const mat = this._terrainMesh.material as THREE.MeshLambertMaterial
    mat.wireframe = mode === 'wireframe'
    if (mode === 'wireframe' || mode === 'density') {
      this._applyDensityColours()
    } else if (mode === 'contour') {
      this._applyContourColours()
    } else if (mode === 'desert') {
      this._applyDesertColours()
    }
  }

  private _applyDensityColours(): void {
    if (!this._terrainMesh) return
    const density = this._densityGrid
    const res     = this._xGrid.length
    const col     = this._terrainMesh.geometry.attributes.color as THREE.BufferAttribute
    for (let ri = 0; ri < res; ri++) {
      const dRow = res - 1 - ri
      for (let ci = 0; ci < res; ci++) {
        const d = density[dRow]?.[ci] ?? 0
        col.setXYZ(ri * res + ci, 0.05 + d*0.10, 0.15 + d*0.35, 0.25 + d*0.45)
      }
    }
    col.needsUpdate = true
  }

  private _applyContourColours(): void {
    if (!this._terrainMesh) return
    const density = this._densityGrid
    const res     = this._xGrid.length
    const col     = this._terrainMesh.geometry.attributes.color as THREE.BufferAttribute
    for (let ri = 0; ri < res; ri++) {
      const dRow = res - 1 - ri
      for (let ci = 0; ci < res; ci++) {
        const d    = density[dRow]?.[ci] ?? 0
        const band = Math.floor(d * 12) % 2
        const v    = band ? 0.45 : 0.20
        col.setXYZ(ri * res + ci, v * 0.30, v * 0.85, v)
      }
    }
    col.needsUpdate = true
  }

  private _applyDesertColours(): void {
    if (!this._terrainMesh || !this._terrainData?.desert) return
    const desert = this._terrainData.desert as number[][]
    const res    = this._xGrid.length
    const col    = this._terrainMesh.geometry.attributes.color as THREE.BufferAttribute
    for (let ri = 0; ri < res; ri++) {
      const dRow = res - 1 - ri
      for (let ci = 0; ci < res; ci++) {
        const d = desert[dRow]?.[ci] ?? 0
        col.setXYZ(ri * res + ci, 0.05 + d * 0.75, 0.03 + d * 0.35, 0.0)
      }
    }
    col.needsUpdate = true
  }

  // ── Build basin boundaries ─────────────────────────────────────────────────

  private _buildBasins(): void {
    if (this._basinBoundaries) {
      this.scene.remove(this._basinBoundaries)
      this._basinBoundaries.geometry.dispose()
      ;(this._basinBoundaries.material as THREE.Material).dispose()
      this._basinBoundaries = null
    }

    const boundaries: number[][] = this._terrainData?.basin_boundaries ?? []
    if (!boundaries.length) return

    const pts: number[] = []
    const RAISE = 0.08  // lift slightly above terrain surface

    for (const seg of boundaries) {
      const [x1, y1, x2, y2] = seg
      const s = this.umapToScene(x1, y1)
      const e = this.umapToScene(x2, y2)
      pts.push(s.x, s.y + RAISE, s.z)
      pts.push(e.x, e.y + RAISE, e.z)
    }

    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pts), 3))

    const mat = new THREE.LineBasicMaterial({ color: 0x1a2a6c, opacity: 0.6, transparent: true })
    this._basinBoundaries = new THREE.LineSegments(geo, mat)
    this.scene.add(this._basinBoundaries)
  }

  // ── Build attractor markers ────────────────────────────────────────────────

  private _buildAttractors(): void {
    if (this._attractorGroup) {
      this.scene.remove(this._attractorGroup)
      this._attractorGroup = null
    }
    for (const m of this._attractorMeshes) {
      m.geometry.dispose()
      ;(m.material as THREE.Material).dispose()
    }
    this._attractorMeshes = []

    const attractors: any[] = this._terrainData?.attractors ?? []
    if (!attractors.length) return

    this._attractorGroup = new THREE.Group()

    for (const attr of attractors) {
      const sp     = this.umapToScene(attr.umap_x, attr.umap_y)
      const radius = attr.is_major ? 0.18 : 0.10
      const color  = attr.is_major ? 0xffffff : 0x888888

      const geo  = new THREE.SphereGeometry(radius, 8, 8)
      const mat  = new THREE.MeshBasicMaterial({ color })
      const mesh = new THREE.Mesh(geo, mat)

      mesh.position.set(sp.x, sp.y + radius * 0.5, sp.z)
      mesh.userData = {
        isMajor: attr.is_major,
        phase:   Math.random() * Math.PI * 2,
      }

      this._attractorMeshes.push(mesh)
      this._attractorGroup.add(mesh)
    }

    this.scene.add(this._attractorGroup)
  }

  // ── Animate attractors ─────────────────────────────────────────────────────

  private _animateAttractors(): void {
    if (!this._attractorMeshes.length) return
    const t = performance.now() * 0.001
    for (const mesh of this._attractorMeshes) {
      const phase = mesh.userData.phase as number
      const pulse = 1 + 0.15 * Math.sin(t * 2.0 + phase)
      mesh.scale.setScalar(pulse)
    }
  }

  // ── Animate deepest marker (Piece 5) ───────────────────────────────────────

  private _animateDeepestMarker(): void {
    if (!this._deepestMarker) return
    const mat = this._deepestMarker.material as THREE.MeshBasicMaterial
    const t   = performance.now() * 0.003
    mat.opacity = 0.5 + 0.4 * Math.sin(t)
  }

  // ── Build concept spheres ─────────────────────────────────────────────────

  private _buildConceptSpheres(): void {
    if (this._conceptSpheres) {
      this.scene.remove(this._conceptSpheres)
      this._conceptSpheres.dispose()
    }

    const concepts = this._conceptData
    if (!concepts.length) return

    const COUNT    = concepts.length
    const geo      = new THREE.SphereGeometry(0.04, 6, 6)
    const mat      = new THREE.MeshBasicMaterial()  // instance colors set via setColorAt(), no vertexColors needed
    const instanced = new THREE.InstancedMesh(geo, mat, COUNT)
    instanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage)

    const dummy  = new THREE.Object3D()
    const colour = new THREE.Color()
    this._conceptPositions = []

    for (let i = 0; i < COUNT; i++) {
      const c        = concepts[i]
      const [ux, uy] = c.position_2d
      const pos      = this.umapToScene(ux, uy)
      pos.y         += 0.05  // lift slightly above terrain
      this._conceptPositions.push(pos.clone())

      dummy.position.copy(pos)
      dummy.updateMatrix()
      instanced.setMatrixAt(i, dummy.matrix)

      colour.set(c.colour ?? '#888888')
      instanced.setColorAt(i, colour)
    }

    instanced.instanceMatrix.needsUpdate = true
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true
    this._conceptSpheres = instanced
    this.scene.add(instanced)

    // Re-apply any active filter (e.g. concepts reloaded while filter is on)
    if (this._rogetClassId !== null) this.applyRogetFilter(this._rogetClassId)
    // Rebuild atmosphere if on and no filter (filter path rebuilds inside applyRogetFilter)
    else if (this._atmosphereOn) this._buildAtmosphere()
  }

  // ── Roget filter ──────────────────────────────────────────────────────────

  applyRogetFilter(classId: number | null): void {
    this._rogetClassId = classId
    if (!this._conceptSpheres) return

    const concepts = this._conceptData
    const dummy    = new THREE.Object3D()
    const colour   = new THREE.Color()
    const DIM      = 0.08

    for (let i = 0; i < concepts.length; i++) {
      const c        = concepts[i]
      const matches  = classId === null || c.roget_class_id === classId
      const [ux, uy] = c.position_2d
      const pos      = this.umapToScene(ux, uy)
      pos.y         += 0.05
      const scale    = matches ? 1.0 : 0.3

      dummy.position.copy(pos)
      dummy.scale.setScalar(scale)
      dummy.updateMatrix()
      this._conceptSpheres.setMatrixAt(i, dummy.matrix)

      if (this._tortuosityMode && typeof c.tortuosity === 'number') {
        colour.copy(this._tortuosityToColour(c.tortuosity))
      } else {
        colour.set(c.colour ?? '#888888')
      }
      if (!matches) colour.multiplyScalar(DIM)
      this._conceptSpheres.setColorAt(i, colour)
    }

    this._conceptSpheres.instanceMatrix.needsUpdate = true
    if (this._conceptSpheres.instanceColor) {
      this._conceptSpheres.instanceColor.needsUpdate = true
    }

    // Rebuild atmosphere to match updated filter
    if (this._atmosphereOn) this._buildAtmosphere()
  }

  // ── Tortuosity colour mode ────────────────────────────────────────────────

  setTortuosityMode(on: boolean): void {
    this._tortuosityMode = on
    this.applyRogetFilter(this._rogetClassId)
  }

  isTortuosityMode(): boolean { return this._tortuosityMode }

  private _tortuosityToColour(t: number): THREE.Color {
    // Stops: 1.0→deep-blue, ~4→teal, ~7→gold, 10+→orange
    // Normalize: t=1.0 → 0, t=10.0 → 1.0, clamp.
    const n = Math.max(0, Math.min((t - 1.0) / 9.0, 1.0))
    // Four colour stops at positions 0, 0.33, 0.67, 1.0
    const stops: [number, number, number][] = [
      [0x1a / 255, 0x3a / 255, 0x6a / 255],  // deep blue   #1a3a6a
      [0x2a / 255, 0x8a / 255, 0x5a / 255],  // teal/green  #2a8a5a
      [0xff / 255, 0xcc / 255, 0x00 / 255],  // bright gold #ffcc00
      [0xff / 255, 0x66 / 255, 0x00 / 255],  // hot orange  #ff6600
    ]
    const seg = n * (stops.length - 1)
    const i   = Math.min(Math.floor(seg), stops.length - 2)
    const f   = seg - i
    const s0  = stops[i], s1 = stops[i + 1]
    return new THREE.Color(
      s0[0] + f * (s1[0] - s0[0]),
      s0[1] + f * (s1[1] - s0[1]),
      s0[2] + f * (s1[2] - s0[2]),
    )
  }

  // ── Probe visualization (Piece 5) ─────────────────────────────────────────

  drawProbe(result: any): void {
    this.clearProbe()
    if (!result?.steps?.length) return

    this._probeGroup = new THREE.Group()

    const steps     = result.steps     as any[]
    const maxDesert = result.desert_max as number

    const termA = this._conceptData.find((c: any) => c.label === result.term_a)
    const termB = this._conceptData.find((c: any) => c.label === result.term_b)
    if (!termA || !termB) return

    const posA = this.umapToScene(termA.position_2d[0], termA.position_2d[1])
    const posB = this.umapToScene(termB.position_2d[0], termB.position_2d[1])

    const colLow  = new THREE.Color(0x1a4fff)  // blue  = near concepts
    const colHigh = new THREE.Color(0xff4400)  // red   = deep desert

    // Tube line with per-vertex colour
    const positions: number[] = []
    const colours:   number[] = []
    for (const step of steps) {
      const t   = step.alpha as number
      const pos = posA.clone().lerp(posB, t)
      pos.y    += 0.1
      const d   = Math.min((step.desert_value as number) / Math.max(maxDesert, 0.001), 1)
      const col = colLow.clone().lerp(colHigh, d)
      positions.push(pos.x, pos.y, pos.z)
      colours.push(col.r, col.g, col.b)
    }

    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    lineGeo.setAttribute('color',    new THREE.Float32BufferAttribute(colours, 3))
    this._probeGroup.add(new THREE.Line(lineGeo,
      new THREE.LineBasicMaterial({ vertexColors: true, linewidth: 2 })))

    // Step nodes scaled by desert value
    for (let i = 0; i < steps.length; i++) {
      const step  = steps[i]
      const t     = step.alpha as number
      const pos   = posA.clone().lerp(posB, t)
      pos.y      += 0.1
      const d     = Math.min((step.desert_value as number) / Math.max(maxDesert, 0.001), 1)
      const scale = 0.012 + d * 0.023
      const col   = colLow.clone().lerp(colHigh, d)
      const node  = new THREE.Mesh(
        new THREE.SphereGeometry(scale, 6, 6),
        new THREE.MeshBasicMaterial({ color: col }),
      )
      node.position.copy(pos)
      node.userData = {
        stepIndex:   i,
        desertValue: step.desert_value,
        nearestTerm: step.nearest_term,
      }
      this._probeGroup.add(node)
    }

    // Deepest point ring marker
    const deepIdx = result.deepest_step_index as number
    if (deepIdx >= 0 && deepIdx < steps.length) {
      const deepPos = posA.clone().lerp(posB, steps[deepIdx].alpha as number)
      deepPos.y    += 0.12
      const ringGeo = new THREE.RingGeometry(0.06, 0.09, 32)
      ringGeo.rotateX(-Math.PI / 2)
      this._deepestMarker = new THREE.Mesh(ringGeo,
        new THREE.MeshBasicMaterial({
          color: 0xffee00, transparent: true, opacity: 0.9, side: THREE.DoubleSide,
        }),
      )
      this._deepestMarker.position.copy(deepPos)
      this._deepestMarker.userData = { birthTime: performance.now() }
      this.scene.add(this._deepestMarker)
    }

    this.scene.add(this._probeGroup)
  }
  clearProbe(): void {
    if (this._probeGroup) {
      this.scene.remove(this._probeGroup)
      this._probeGroup = null
    }
    if (this._deepestMarker) {
      this.scene.remove(this._deepestMarker)
      this._deepestMarker = null
    }
  }

  // ── Voronoi vertices ──────────────────────────────────────────────────────

  loadVoronoi(vertices: any[]): void {
    this.clearVoronoi()
    if (!vertices.length) return

    this._voronoiData = vertices
    const COUNT = vertices.length
    const geo   = new THREE.IcosahedronGeometry(0.09, 0)
    const mat   = new THREE.MeshBasicMaterial({
      color: 0xffffff, wireframe: true, opacity: 0.6, transparent: true,
    })
    const mesh = new THREE.InstancedMesh(geo, mat, COUNT)
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)

    const dummy = new THREE.Object3D()
    for (let i = 0; i < COUNT; i++) {
      const v   = vertices[i]
      const pos = this.umapToScene(v.x, v.y)
      pos.y    += 0.12
      dummy.position.copy(pos)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)
    }
    mesh.instanceMatrix.needsUpdate = true
    this._voronoiMesh = mesh
    this.scene.add(mesh)
  }

  clearVoronoi(): void {
    if (this._voronoiMesh) {
      this.scene.remove(this._voronoiMesh)
      this._voronoiMesh.geometry.dispose()
      ;(this._voronoiMesh.material as THREE.Material).dispose()
      this._voronoiMesh = null
    }
    this._voronoiData = []
  }

  showVoronoi(visible: boolean): void {
    if (this._voronoiMesh) this._voronoiMesh.visible = visible
  }

  pickVoronoi(clientX: number, clientY: number): any | null {
    if (!this._voronoiMesh || !this._canvas) return null
    const rect = this._canvas.getBoundingClientRect()
    const ndcX =  ((clientX - rect.left) / rect.width)  * 2 - 1
    const ndcY = -((clientY - rect.top)  / rect.height) * 2 + 1
    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), this.camera)
    const hits = raycaster.intersectObject(this._voronoiMesh)
    if (hits.length > 0 && hits[0].instanceId !== undefined) {
      return this._voronoiData[hits[0].instanceId] ?? null
    }
    return null
  }

  // ── Concept path ──────────────────────────────────────────────────────────

  drawConceptPath(result: any): void {
    this.clearConceptPath()
    const steps: any[] = result?.steps ?? []
    if (steps.length < 2) return

    this._pathGroup = new THREE.Group()
    this._pathWaypoints = []
    this._pathWaypointIndex = 0

    // Build waypoint positions
    const pts: THREE.Vector3[] = steps.map((s: any) => {
      const p = this.umapToScene(s.position_2d[0], s.position_2d[1])
      p.y += 0.25
      return p
    })
    this._pathWaypoints = pts

    // TubeGeometry through waypoints
    const curve    = new THREE.CatmullRomCurve3(pts)
    const segments = Math.max(pts.length * 4, 64)
    const tubeGeo  = new THREE.TubeGeometry(curve, segments, 0.025, 6, false)
    const tubeMat  = new THREE.MeshBasicMaterial({
      color: 0xffffff, transparent: true, opacity: 0.75,
    })
    this._pathGroup.add(new THREE.Mesh(tubeGeo, tubeMat))

    // Waypoint spheres
    const sphereGeo = new THREE.SphereGeometry(0.06, 8, 8)
    for (let i = 0; i < pts.length; i++) {
      const isEnd = i === 0 || i === pts.length - 1
      const mat   = new THREE.MeshBasicMaterial({ color: isEnd ? 0x00d4ff : 0xffffff })
      const node  = new THREE.Mesh(sphereGeo, mat)
      node.position.copy(pts[i])
      node.userData = { pathStep: i, term: steps[i].term }
      this._pathGroup.add(node)
    }

    this.scene.add(this._pathGroup)
  }

  clearConceptPath(): void {
    if (this._pathGroup) {
      this.scene.remove(this._pathGroup)
      this._pathGroup = null
    }
    this._pathWaypoints     = []
    this._pathWaypointIndex = 0
  }

  stepConceptPath(dir: 1 | -1): void {
    if (!this._pathWaypoints.length) return
    this._pathWaypointIndex = Math.max(
      0,
      Math.min(this._pathWaypoints.length - 1, this._pathWaypointIndex + dir),
    )
    this.flyTo(this._pathWaypoints[this._pathWaypointIndex], 600)
  }

  getPathWaypointIndex(): number { return this._pathWaypointIndex }
  getPathLength(): number        { return this._pathWaypoints.length }

  // ── Dispose ────────────────────────────────────────────────────────────────

  dispose(): void {
    cancelAnimationFrame(this._animFrameId)
    if (this._terrainMesh)     { this.scene.remove(this._terrainMesh);     this._terrainMesh = null }
    if (this._conceptSpheres)  { this.scene.remove(this._conceptSpheres);  this._conceptSpheres = null }
    if (this._basinFill)       { this.scene.remove(this._basinFill);       this._basinFill = null }
    if (this._basinBoundaries) { this.scene.remove(this._basinBoundaries); this._basinBoundaries = null }
    if (this._attractorGroup)  { this.scene.remove(this._attractorGroup);  this._attractorGroup = null }
    for (const m of this._attractorMeshes) {
      m.geometry.dispose()
      ;(m.material as THREE.Material).dispose()
    }
    this._attractorMeshes = []
    this._clearAtmosphere()
    this._terrainData = null
    this.renderer.dispose()
    SceneManager._instance = null
    this._initialized = false
  }

  // ── Journal markers (Piece 6) ─────────────────────────────────────────────

  addJournalMarker(entry: any): void {
    if (!this._journalGroup) {
      this._journalGroup = new THREE.Group()
      this.scene.add(this._journalGroup)
    }

    const [ux, uy] = entry.coordinates_2d as [number, number]
    const isStarred = entry.starred    as boolean
    const desert    = entry.desert_value as number

    const col = isStarred      ? 0xffd700
              : desert >= 0.05 ? 0xff4400
              : 0xffffff

    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.06, 8, 8),
      new THREE.MeshBasicMaterial({ color: col }),
    )

    // [0,0] means no UMAP position (CLI discovery) — skip 3D marker
    if (ux === 0 && uy === 0) return

    const pos = this.umapToScene(ux, uy)
    pos.y    += 0.2
    mesh.position.copy(pos)

    mesh.userData = { journalId: entry.id, entryType: entry.type }
    this._journalGroup.add(mesh)
  }

  async loadJournalMarkers(): Promise<void> {
    try {
      const resp = await fetch('/api/journal?limit=500')
      if (!resp.ok) return
      const data = await resp.json()
      for (const entry of (data.entries ?? [])) {
        this.addJournalMarker(entry)
      }
    } catch (_) {
      // Journal may be empty or unavailable — not an error
    }
  }
  clearJournalMarkers(): void {
    if (this._journalGroup) {
      this.scene.remove(this._journalGroup)
      this._journalGroup = new THREE.Group()
      this.scene.add(this._journalGroup)
    }
  }

  // ── Nearest concept query (for proximity panel) ───────────────────────────

  getNearestConcepts(k = 8): any[] {
    if (!this._conceptData.length) return []
    const cam = this.camera.position
    return [...this._conceptData]
      .filter(c => c.position_2d)
      .map(c => {
        const sp = this.umapToScene(c.position_2d[0], c.position_2d[1])
        return { ...c, _dist: cam.distanceTo(sp) }
      })
      .sort((a, b) => a._dist - b._dist)
      .slice(0, k)
  }

  // ── Concept picking (hover) ───────────────────────────────────────────────

  /**
   * Raycast against concept spheres at the given client-space mouse position.
   * Returns the concept data object for the hit sphere, or null.
   */
  pickConcept(clientX: number, clientY: number): any | null {
    if (!this._conceptSpheres || !this._canvas) return null

    const rect = this._canvas.getBoundingClientRect()
    const ndcX =  ((clientX - rect.left) / rect.width)  * 2 - 1
    const ndcY = -((clientY - rect.top)  / rect.height) * 2 + 1

    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), this.camera)

    const hits = raycaster.intersectObject(this._conceptSpheres)
    if (hits.length > 0 && hits[0].instanceId !== undefined) {
      return this._conceptData[hits[0].instanceId] ?? null
    }
    return null
  }

  // ── Atmosphere layer ──────────────────────────────────────────────────────

  setAtmosphere(on: boolean): void {
    this._atmosphereOn = on
    if (on) {
      this._buildAtmosphere()
    } else {
      this._clearAtmosphere()
    }
  }

  isAtmosphereOn(): boolean { return this._atmosphereOn }

  private _clearAtmosphere(): void {
    if (this._atmSpheres) {
      this.scene.remove(this._atmSpheres)
      this._atmSpheres.dispose()
      this._atmSpheres = null
    }
    if (this._atmFilaments) {
      this.scene.remove(this._atmFilaments)
      this._atmFilaments.geometry.dispose()
      ;(this._atmFilaments.material as THREE.Material).dispose()
      this._atmFilaments = null
    }
    if (this._atmHullGroup) {
      this.scene.remove(this._atmHullGroup)
      this._atmHullGroup.children.forEach(child => {
        const m = child as THREE.Mesh
        m.geometry?.dispose()
        ;(m.material as THREE.Material)?.dispose()
      })
      this._atmHullGroup = null
    }
    this._variantMeta = []
  }

  private _buildAtmosphere(): void {
    this._clearAtmosphere()
    if (!this._conceptData.length || !this._xGrid.length) return

    // Filter candidates: polysemy above threshold, matching active Roget filter
    const candidates = this._conceptData
      .map((c: any, i: number) => ({ c, i }))
      .filter(({ c }: { c: any }) => {
        const poly = c.polysemy_score ?? 0
        if (poly <= this._ATM_MIN_POLYSEMY) return false
        if (this._rogetClassId !== null && c.roget_class_id !== this._rogetClassId) return false
        if (!Array.isArray(c.contexts) || c.contexts.length !== 7) return false
        return true
      })

    // Sort by polysemy descending so the cap keeps the most interesting terms
    candidates.sort((a: any, b: any) =>
      (b.c.polysemy_score ?? 0) - (a.c.polysemy_score ?? 0)
    )

    const maxConcepts = Math.floor(this._ATM_MAX_VARIANTS / 7)
    const filtered    = candidates.slice(0, maxConcepts)
    if (filtered.length === 0) return

    const totalVariants = filtered.length * 7
    const sphereGeo = new THREE.SphereGeometry(0.025, 5, 5)
    const sphereMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.5 })
    const instanced = new THREE.InstancedMesh(sphereGeo, sphereMat, totalVariants)
    instanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage)

    const dummy       = new THREE.Object3D()
    const colour      = new THREE.Color()
    const linePos:    number[] = []
    const lineColRgb: number[] = []
    this._variantMeta = []

    let hullCount = 0
    this._atmHullGroup = new THREE.Group()

    let instanceIdx = 0
    for (const { c, i: conceptIndex } of filtered) {
      const basePos = this.umapToScene(c.position_2d[0], c.position_2d[1])
      basePos.y += 0.05  // same lift as base concept spheres

      colour.set(c.colour ?? '#888888')
      const { r, g, b } = colour

      for (let ci = 0; ci < 7; ci++) {
        const ctx              = c.contexts[ci]
        const [vx, vy]         = ctx.position_2d as [number, number]
        const varPos           = this.umapToScene(vx, vy)
        varPos.y              += 0.3  // float above terrain height + 0.3

        dummy.position.copy(varPos)
        dummy.updateMatrix()
        instanced.setMatrixAt(instanceIdx, dummy.matrix)
        instanced.setColorAt(instanceIdx, colour)

        this._variantMeta.push({ conceptIndex, contextIndex: ci })

        // Filament: base concept → variant sphere
        linePos.push(basePos.x, basePos.y, basePos.z)
        linePos.push(varPos.x,  varPos.y,  varPos.z)
        lineColRgb.push(r, g, b, r, g, b)  // 2 vertices × 3 floats

        instanceIdx++
      }

      // Convex hull approximation for highly polysemous terms
      if ((c.polysemy_score ?? 0) > this._ATM_HULL_POLYSEMY && hullCount < this._ATM_MAX_HULLS) {
        const spread   = c.context_spread ?? 0.1
        const hullGeo  = new THREE.SphereGeometry(Math.max(spread * 0.5, 0.05), 8, 8)
        const hullMat  = new THREE.MeshBasicMaterial({
          color: c.colour ?? '#888888',
          transparent: true,
          opacity: 0.10,
          side: THREE.DoubleSide,
          depthWrite: false,
        })
        const hullMesh = new THREE.Mesh(hullGeo, hullMat)
        hullMesh.position.copy(basePos)
        hullMesh.position.y += 0.15
        this._atmHullGroup.add(hullMesh)
        hullCount++
      }
    }

    instanced.instanceMatrix.needsUpdate = true
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true
    this._atmSpheres = instanced
    this.scene.add(instanced)

    // Filaments — single LineSegments draw call, per-vertex colour at 25% opacity
    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePos,    3))
    lineGeo.setAttribute('color',    new THREE.Float32BufferAttribute(lineColRgb, 3))
    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.25,
    })
    this._atmFilaments = new THREE.LineSegments(lineGeo, lineMat)
    this.scene.add(this._atmFilaments)

    if (this._atmHullGroup.children.length > 0) {
      this.scene.add(this._atmHullGroup)
    }
  }

  /**
   * Raycast against atmosphere variant spheres.
   * Returns { concept, contextKey, distFromBase } or null.
   */
  pickVariant(clientX: number, clientY: number): {
    concept: any; contextKey: string; distFromBase: number
  } | null {
    if (!this._atmSpheres || !this._atmosphereOn || !this._canvas) return null

    const rect = this._canvas.getBoundingClientRect()
    const ndcX =  ((clientX - rect.left) / rect.width)  * 2 - 1
    const ndcY = -((clientY - rect.top)  / rect.height) * 2 + 1

    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), this.camera)

    const hits = raycaster.intersectObject(this._atmSpheres)
    if (hits.length > 0 && hits[0].instanceId !== undefined) {
      const meta        = this._variantMeta[hits[0].instanceId]
      if (!meta) return null
      const concept     = this._conceptData[meta.conceptIndex]
      const contextKey  = this._CONTEXT_KEYS[meta.contextIndex]
      const ctx         = concept?.contexts?.[meta.contextIndex]
      const distFromBase = ctx?.distance_from_base ?? 0
      return { concept, contextKey, distFromBase }
    }
    return null
  }
}
