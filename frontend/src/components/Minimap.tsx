import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { SceneManager } from '../scene/SceneManager'
import { ROGET_CLASS_COLOURS } from '../types'
import type { RogetClassId } from '../types'

const SIZE = 160  // canvas size in pixels

export default function Minimap() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const draw = () => {
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const sm     = SceneManager.getInstance()
      const sm_any = sm as any

      const xGrid    = sm_any._xGrid    as number[]
      const yGrid    = sm_any._yGrid    as number[]
      const density  = sm_any._densityGrid as number[][]
      const concepts = sm_any._conceptData as any[]

      if (!xGrid.length) return

      const xMin = xGrid[0],            xMax = xGrid[xGrid.length - 1]
      const yMin = yGrid[0],            yMax = yGrid[yGrid.length - 1]
      const w    = xMax - xMin,         h    = yMax - yMin

      const toCanvas = (ux: number, uy: number): [number, number] => [
        ((ux - xMin) / w) * SIZE,
        SIZE - ((uy - yMin) / h) * SIZE,  // y-flip: UMAP y+ up, canvas y+ down
      ]

      // Clear
      ctx.fillStyle = '#0a0a0f'
      ctx.fillRect(0, 0, SIZE, SIZE)

      // Density heatmap
      const res   = xGrid.length
      const cellW = SIZE / res
      const cellH = SIZE / res
      for (let ri = 0; ri < res; ri++) {
        for (let ci = 0; ci < res; ci++) {
          const d   = density[ri]?.[ci] ?? 0
          const b   = Math.floor(d * 60)
          ctx.fillStyle = `rgb(${b},${b + 20},${b + 40})`
          ctx.fillRect(ci * cellW, (res - 1 - ri) * cellH, cellW + 1, cellH + 1)
        }
      }

      // Concept dots (sample up to 2000 for performance)
      const step = Math.max(1, Math.floor(concepts.length / 2000))
      ctx.globalAlpha = 0.6
      for (let i = 0; i < concepts.length; i += step) {
        const c = concepts[i]
        if (!c.position_2d) continue
        const [px, py] = toCanvas(c.position_2d[0], c.position_2d[1])
        ctx.fillStyle = ROGET_CLASS_COLOURS[c.roget_class_id as RogetClassId] ?? '#888'
        ctx.fillRect(px - 0.7, py - 0.7, 1.4, 1.4)
      }
      ctx.globalAlpha = 1.0

      // Camera position + direction
      const cam  = sm.camera.position
      const [cx, cy] = toCanvas(cam.x, -cam.z)  // reverse y-flip from umapToScene

      // Direction line from quaternion
      const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(sm.camera.quaternion)
      const [dx, dy] = toCanvas(cam.x + fwd.x * 3, -cam.z - fwd.z * 3)
      ctx.strokeStyle = '#00b4d8'
      ctx.lineWidth   = 1.5
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(dx, dy)
      ctx.stroke()

      // Position dot
      ctx.fillStyle = '#00b4d8'
      ctx.beginPath()
      ctx.arc(cx, cy, 3, 0, Math.PI * 2)
      ctx.fill()
    }

    const id = setInterval(draw, 200)
    draw()
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      position:'absolute', bottom:'1rem', right:'1rem',
      border:'1px solid #222', borderRadius:'4px',
      overflow:'hidden', userSelect:'none',
    }}>
      <canvas
        ref={canvasRef}
        width={SIZE}
        height={SIZE}
        style={{ display:'block', width:SIZE, height:SIZE }}
      />
    </div>
  )
}
