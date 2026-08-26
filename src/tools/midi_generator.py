"""
Generador de Archivos MIDI Reales (.mid) en Python puro para Yuki.
Crea pistas polifónicas y multipista con escalas tradicionales japonesas (Insen, Hirajoshi, Kumoi)
y líneas de bajo orgánico / lofi sin dependencias externas.
"""

import struct
import os
import time
from typing import List, Dict, Any, Tuple

# Escalas Tradicionales Japonesas (intervalos desde tónica en semitonos)
JAPANESE_SCALES = {
    "insen": [0, 1, 5, 7, 10],      # Insen (C, Db, F, G, Bb) - Melancólica / Tradicional
    "hirajoshi": [0, 2, 3, 7, 8],   # Hirajoshi (C, D, Eb, G, Ab) - Sublime / Koto clásico
    "kumoi": [0, 2, 3, 7, 9],       # Kumoi (C, D, Eb, G, A) - Estacional / Solemne
    "iwato": [0, 1, 5, 6, 10],      # Iwato (C, Db, F, Gb, Bb) - Tensión y misterio
    "yo": [0, 2, 5, 7, 9]           # Escala Yo (C, D, F, G, A) - Festiva / Luminosa
}

def var_length(val: int) -> bytes:
    """Codifica un entero en formato variable-length de MIDI."""
    buffer = val & 0x7F
    while val >> 7:
        val >>= 7
        buffer <<= 8
        buffer |= (val & 0x7F) | 0x80
    res = bytearray()
    while True:
        res.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break
    return bytes(res)

class MIDITrackBuilder:
    def __init__(self, track_name: str = "Shamisen"):
        self.events: List[Tuple[int, bytes]] = [] # (delta_time_ticks, event_bytes)
        self.track_name = track_name
        self._add_meta_name(track_name)

    def _add_meta_name(self, name: str):
        name_bytes = name.encode("utf-8")
        self.events.append((0, b"\xFF\x03" + bytes([len(name_bytes)]) + name_bytes))

    def set_instrument(self, channel: int, program: int):
        """Programa de instrumento MIDI (ej. 105 = Banjo/Shamisen, 107 = Koto, 32 = Acoustic Bass)."""
        self.events.append((0, bytes([0xC0 | (channel & 0x0F), program & 0x7F])))

    def note_on(self, channel: int, note: int, velocity: int = 80, delta_ticks: int = 0):
        self.events.append((delta_ticks, bytes([0x90 | (channel & 0x0F), note & 0x7F, velocity & 0x7F])))

    def note_off(self, channel: int, note: int, delta_ticks: int = 480):
        self.events.append((delta_ticks, bytes([0x80 | (channel & 0x0F), note & 0x7F, 0x00])))

    def build_chunk(self) -> bytes:
        data = bytearray()
        for delta, evt in self.events:
            data.extend(var_length(delta))
            data.extend(evt)
        # End of Track
        data.extend(var_length(0))
        data.extend(b"\xFF\x2F\x00")
        
        chunk = b"MTrk" + struct.pack(">I", len(data)) + bytes(data)
        return chunk

class YukiMIDIGenerator:
    def __init__(self, ticks_per_beat: int = 480):
        self.ticks_per_beat = ticks_per_beat

    def generate_track(
        self,
        title: str,
        scale_name: str = "insen",
        root_note: int = 60, # 60 = C4
        bpm: int = 84,
        num_bars: int = 16,
        output_dir: str = "output/music"
    ) -> Dict[str, Any]:
        """
        Genera un archivo MIDI multipista completo y válido:
        - Pista 0: Tempo y Metadatos
        - Pista 1: Shamisen Lead (melodía con pausas Ma)
        - Pista 2: Koto Arpegios (armonía estacional)
        - Pista 3: 808 Sub-bass (raíz de acero industrial)
        """
        os.makedirs(output_dir, exist_ok=True)
        scale_intervals = JAPANESE_SCALES.get(scale_name.lower(), JAPANESE_SCALES["insen"])
        
        # 1. Pista 0: Tempo y Time Signature
        track0 = MIDITrackBuilder("Conductor")
        us_per_beat = int(60_000_000 / bpm)
        track0.events.append((0, b"\xFF\x51\x03" + struct.pack(">I", us_per_beat)[1:]))
        track0.events.append((0, b"\xFF\x58\x04\x04\x02\x18\x08")) # 4/4 time signature

        # 2. Pista 1: Shamisen Lead
        track_shamisen = MIDITrackBuilder("Yuki Shamisen Lead")
        track_shamisen.set_instrument(channel=0, program=105) # Sitar/Shamisen equivalent in GM

        # 3. Pista 2: Koto Arpegios
        track_koto = MIDITrackBuilder("Koto Ambient Texture")
        track_koto.set_instrument(channel=1, program=107) # Koto in GM

        # 4. Pista 3: Sub-Bass 808
        track_bass = MIDITrackBuilder("Industrial Sub-Bass")
        track_bass.set_instrument(channel=2, program=38) # Synth Bass 1 in GM

        # Composición algorítmica con pausas Ma
        lead_scale_notes = [root_note + interval for interval in scale_intervals]
        lead_scale_notes += [root_note + 12 + interval for interval in scale_intervals]

        # Generar compases
        for bar in range(num_bars):
            # Línea de bajo (notas tónicas en los compases)
            bass_note = root_note - 24 + scale_intervals[bar % len(scale_intervals)]
            track_bass.note_on(channel=2, note=bass_note, velocity=95, delta_ticks=0)
            track_bass.note_off(channel=2, note=bass_note, delta_ticks=self.ticks_per_beat * 4)

            # Shamisen Lead con pausas
            if bar % 4 != 3: # El 4to compás es silencio (Ma)
                for beat in range(4):
                    note_idx = (bar * 2 + beat) % len(lead_scale_notes)
                    note = lead_scale_notes[note_idx]
                    track_shamisen.note_on(channel=0, note=note, velocity=85, delta_ticks=0)
                    track_shamisen.note_off(channel=0, note=note, delta_ticks=self.ticks_per_beat)
            else:
                # Silencio en shamisen durante un compás entero
                pass

            # Koto textura de fondo (notas sostenidas)
            koto_note = root_note - 12 + scale_intervals[(bar + 2) % len(scale_intervals)]
            track_koto.note_on(channel=1, note=koto_note, velocity=60, delta_ticks=0)
            track_koto.note_off(channel=1, note=koto_note, delta_ticks=self.ticks_per_beat * 4)

        # Ensamblado del archivo MIDI Type 1
        tracks = [track0, track_shamisen, track_koto, track_bass]
        header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), self.ticks_per_beat)
        
        midi_data = bytearray(header)
        for t in tracks:
            midi_data.extend(t.build_chunk())

        filename = f"{title.lower().replace(' ', '_')}_{int(time.time())}.mid"
        file_path = os.path.join(output_dir, filename)

        with open(file_path, "wb") as f:
            f.write(midi_data)

        return {
            "status": "success",
            "file_path": file_path,
            "filename": filename,
            "title": title,
            "scale": scale_name,
            "bpm": bpm,
            "bars": num_bars,
            "size_bytes": len(midi_data)
        }
