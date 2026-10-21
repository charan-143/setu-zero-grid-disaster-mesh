"""
Offline MBTiles Topographic Tile Pack Server
Serves pre-packaged vector/raster map tiles from a local SQLite-based MBTiles database,
completely eliminating reliance on public CDNs, internet access, or external map APIs.
"""

import sqlite3
import os
from typing import Optional, Tuple


class LocalMbTilesServer:
    """
    Manages local .mbtiles file (standard SQLite format defined by Mapbox).
    Tables:
    - metadata (name, format, bounds, center, minzoom, maxzoom)
    - tiles (zoom_level, tile_column, tile_row, tile_data)
    """

    def __init__(self, mbtiles_path: str = "district_topography.mbtiles"):
        self.mbtiles_path = mbtiles_path
        self._init_mock_or_real_db()

    def _init_mock_or_real_db(self):
        """Initializes MBTiles database structure if not already present."""
        with sqlite3.connect(self.mbtiles_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    name TEXT,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tiles (
                    zoom_level INTEGER,
                    tile_column INTEGER,
                    tile_row INTEGER,
                    tile_data BLOB,
                    PRIMARY KEY (zoom_level, tile_column, tile_row)
                )
            """)

            # Populate metadata if empty
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM metadata")
            if cursor.fetchone()[0] == 0:
                metadata_rows = [
                    ("name", "Setu Tactical Offline Topography"),
                    ("format", "png"),
                    ("minzoom", "10"),
                    ("maxzoom", "16"),
                    ("bounds", "85.70,20.20,85.95,20.40"),
                    ("center", "85.8245,20.2961,13"),
                    ("attribution", "NDMA Offline Topo Data")
                ]
                conn.executemany("INSERT INTO metadata VALUES (?, ?)", metadata_rows)
            conn.commit()

    def get_tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        """
        Retrieves raw PNG/JPEG tile bytes from MBTiles SQLite store.
        Note: MBTiles uses TMS y-coordinates (flipped: (1 << z) - 1 - y).
        """
        tms_y = (1 << z) - 1 - y
        with sqlite3.connect(self.mbtiles_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                (z, x, tms_y)
            )
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
        return None

    def get_metadata(self) -> dict:
        data = {}
        with sqlite3.connect(self.mbtiles_path) as conn:
            cursor = conn.cursor()
            for k, v in cursor.execute("SELECT name, value FROM metadata"):
                data[k] = v
        return data
