import * as THREE from 'three'
import type { SurfaceMode } from '../types'

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
    window.addEventListener('keydown', e => { this._keys[e.code] = true })
    window.addEventListener('keyup',   e => { this._keys[e.code] = false })

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
    }
  }

  flyTo(scenePos: THREE.Vector3, duration = 1200): void {
    const start     = this.camera.position.clone()
    const target    = scenePos.clone().add(new THREE.Vector3(0, 3, 3))
    const startTime = performance.now()
    const animate   = () => {
      const t    = Math.min((performance.now() - startTime) / duration, 1)
      const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t
      this.camera.position.lerpVectors(start, target, ease)
      this.camera.lookAt(scenePos)
      if (t < 1) requestAnimationFrame(animate)
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

  // ── Build terrain mesh (Piece 2) ───────────────────────────────────────────

  private _buildTerrainMesh(): void { /* see Piece 2 */ }
  private _buildBasins():      void { /* see Piece 2 */ }
  private _buildAttractors():  void { /* see Piece 2 */ }

  // ── Build concept spheres (Piece 3) ───────────────────────────────────────

  private _buildConceptSpheres(): void { /* see Piece 3 */ }

  // ── Animate (Pieces 2, 5) ──────────────────────────────────────────────────

  private _animateAttractors():    void { /* see Piece 2 */ }
  private _animateDeepestMarker(): void { /* see Piece 5 */ }

  // ── Surface mode (Piece 2) ─────────────────────────────────────────────────

  setSurfaceMode(_mode: SurfaceMode): void { /* see Piece 2 */ }

  // ── Roget filter (Piece 3) ────────────────────────────────────────────────

  applyRogetFilter(_classId: number | null): void { /* see Piece 3 */ }

  // ── Probe visualization (Piece 5) ─────────────────────────────────────────

  drawProbe(_result: any): void { /* see Piece 5 */ }
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

  // ── Dispose ────────────────────────────────────────────────────────────────

  dispose(): void {
    cancelAnimationFrame(this._animFrameId)
    if (this._terrainMesh)     { this.scene.remove(this._terrainMesh);     this._terrainMesh = null }
    if (this._conceptSpheres)  { this.scene.remove(this._conceptSpheres);  this._conceptSpheres = null }
    if (this._basinFill)       { this.scene.remove(this._basinFill);       this._basinFill = null }
    if (this._basinBoundaries) { this.scene.remove(this._basinBoundaries); this._basinBoundaries = null }
    if (this._attractorGroup)  { this.scene.remove(this._attractorGroup);  this._attractorGroup = null }
    void this._terrainData  // scaffold: read to satisfy noUnusedLocals
    this._terrainData = null
    this.renderer.dispose()
    SceneManager._instance = null
    this._initialized = false
  }

  // ── Journal markers (Piece 6) ─────────────────────────────────────────────

  addJournalMarker(_entry: any): void { /* see Piece 6 */ }
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
}
