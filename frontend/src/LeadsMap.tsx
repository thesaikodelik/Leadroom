// The run's leads on a map. Tiles come from OpenFreeMap: no key, no account and no
// download; only the viewed area is fetched while the map is open. Leads without a map
// position are not plotted here and stay in the list beside it.

import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// Vite bundles the worker with its imports; maplibre otherwise looks beside its own file.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Lead } from './types'

const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'

maplibregl.setWorkerUrl(workerUrl)

export type MappedLead = { lead: Lead; lng: number; lat: number }

function token(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

// Repaint the base map in the workspace palette and appearance.
function paintWorld(map: MapLibreMap) {
  const land = token('--map-land')
  const water = token('--map-water')
  const park = token('--map-park')
  const road = token('--map-road')
  const label = token('--map-label')
  const rule = token('--rule')
  const hair = token('--hair')
  for (const layer of map.getStyle()?.layers ?? []) {
    const id = layer.id
    if (id.startsWith('leads')) continue
    try {
      if (layer.type === 'background') map.setPaintProperty(id, 'background-color', land)
      else if (layer.type === 'fill') {
        if (/water|ocean|sea/.test(id)) map.setPaintProperty(id, 'fill-color', water)
        else if (/park|wood|grass|landcover|cemetery|pitch/.test(id)) map.setPaintProperty(id, 'fill-color', park)
        else if (/building/.test(id)) map.setPaintProperty(id, 'fill-color', hair)
        else map.setPaintProperty(id, 'fill-color', land)
      } else if (layer.type === 'line') {
        if (/water/.test(id)) map.setPaintProperty(id, 'line-color', water)
        else if (/boundary/.test(id)) map.setPaintProperty(id, 'line-color', rule)
        else if (/casing/.test(id)) map.setPaintProperty(id, 'line-color', rule)
        else map.setPaintProperty(id, 'line-color', road)
      } else if (layer.type === 'symbol') {
        map.setPaintProperty(id, 'text-color', label)
        map.setPaintProperty(id, 'text-halo-color', land)
      }
    } catch {
      // A layer without that paint property keeps its own colour.
    }
  }
  if (map.getLayer('leads-points')) {
    map.setPaintProperty('leads-points', 'circle-color', ['match', ['get', 'step'], 1, token('--ev-1'), 2, token('--ev-2'), 3, token('--ev-3'), 4, token('--ev-4'), token('--ev-5')])
    map.setPaintProperty('leads-points', 'circle-stroke-color', token('--sheet'))
    map.setPaintProperty('leads-selected', 'circle-stroke-color', token('--action'))
  }
}

function features(points: MappedLead[]) {
  return {
    type: 'FeatureCollection' as const,
    features: points.map(({ lead, lng, lat }) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [lng, lat] },
      properties: {
        domain: lead.domain,
        name: lead.business_name || lead.domain,
        step: Math.max(1, Math.min(5, Math.ceil((Number(lead.lead_score) || 0) / 2))),
      },
    })),
  }
}

export default function LeadsMap({ points, selected, onSelect }: { points: MappedLead[]; selected: string | null; onSelect: (domain: string) => void }) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const onSelectRef = useRef(onSelect)
  const [offline, setOffline] = useState(false)
  const [ready, setReady] = useState(false)
  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])

  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: [-1.6, 52.8],
      zoom: 5,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('error', (event) => {
      const status = (event.error as { status?: number } | undefined)?.status
      if (!status || status >= 500 || status === 0) setOffline(true)
    })
    map.on('load', () => {
      map.addSource('leads', { type: 'geojson', data: features([]) })
      map.addLayer({ id: 'leads-selected', type: 'circle', source: 'leads', filter: ['==', ['get', 'domain'], ''], paint: { 'circle-radius': 13, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-width': 2.5, 'circle-stroke-color': token('--action') } })
      map.addLayer({ id: 'leads-points', type: 'circle', source: 'leads', paint: { 'circle-radius': 7, 'circle-color': token('--ev-4'), 'circle-stroke-width': 2, 'circle-stroke-color': token('--sheet') } })
      map.on('click', 'leads-points', (event) => {
        const domain = event.features?.[0]?.properties?.domain
        if (typeof domain === 'string') onSelectRef.current(domain)
      })
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'lead-popup' })
      map.on('mouseenter', 'leads-points', (event) => {
        map.getCanvas().style.cursor = 'pointer'
        const feature = event.features?.[0]
        if (feature?.geometry.type === 'Point') popup.setLngLat(feature.geometry.coordinates as [number, number]).setText(String(feature.properties?.name ?? '')).addTo(map)
      })
      map.on('mouseleave', 'leads-points', () => { map.getCanvas().style.cursor = ''; popup.remove() })
      paintWorld(map)
      setReady(true)
    })
    // Follow light/dark and palette changes.
    const observer = new MutationObserver(() => { if (map.isStyleLoaded()) paintWorld(map) })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-appearance', 'data-theme'] })
    return () => { observer.disconnect(); map.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource('leads') as GeoJSONSource | undefined)?.setData(features(points))
    if (!points.length) return
    const bounds = new maplibregl.LngLatBounds()
    points.forEach(({ lng, lat }) => bounds.extend([lng, lat]))
    map.fitBounds(bounds, { padding: 56, maxZoom: 14, duration: 0 })
  }, [points, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setFilter('leads-selected', ['==', ['get', 'domain'], selected ?? ''])
    const point = points.find(({ lead }) => lead.domain === selected)
    if (point && !map.getBounds().contains([point.lng, point.lat])) map.easeTo({ center: [point.lng, point.lat], duration: 400 })
  }, [selected, points, ready])

  return <div className="leads-map">
    <div ref={container} className="leads-map-canvas" role="region" aria-label={`Map of ${points.length} leads with a map position`} />
    {!points.length && <div className="leads-map-empty"><strong>No lead in this run has a map position</strong><span>Leads matched in the local map index are plotted here. Every lead stays in the list.</span></div>}
    {offline && <div className="leads-map-offline" role="status">The map needs an internet connection. The list works without it.</div>}
  </div>
}

