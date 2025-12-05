#!/usr/bin/env python3
"""
Wigle Wardriving CSV to KML Converter with Triangulation

This script processes Wigle wardriving CSV files to:
1. Find access points with at least 3 recorded observations
2. Triangulate the likely position of each access point
3. Output a KML file for Google Earth with accuracy circles
"""

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import xml.etree.ElementTree as ET
from xml.dom import minidom


@dataclass
class APObservation:
    """A single observation of an access point"""
    latitude: float
    longitude: float
    signal_strength: int  # in dBm (negative values)
    accuracy: float  # GPS accuracy in meters


@dataclass
class TriangulatedAP:
    """A triangulated access point with estimated position"""
    mac: str
    ssid: str
    latitude: float
    longitude: float
    uncertainty: float  # uncertainty radius in meters
    observation_count: int


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth
    Returns distance in meters
    """
    R = 6371000  # Earth's radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def triangulate_position(observations: List[APObservation]) -> Tuple[float, float, float]:
    """
    Triangulate the position of an AP based on multiple observations
    Uses weighted centroid based on signal strength and GPS accuracy
    
    Returns: (latitude, longitude, uncertainty_radius)
    """
    if not observations:
        raise ValueError("No observations provided")
    
    # Convert signal strength to weights (stronger signal = higher weight)
    # dBm values are negative, so we normalize them
    # Also factor in GPS accuracy (lower accuracy value = higher weight)
    weights = []
    for obs in observations:
        # Signal strength weight: convert dBm to linear scale
        # Typical range is -30 (very strong) to -90 (very weak)
        signal_weight = 10 ** (obs.signal_strength / 10)
        
        # GPS accuracy weight: inverse relationship
        # Add 1 to avoid division by zero
        accuracy_weight = 1 / (obs.accuracy + 1)
        
        # Combined weight
        weight = signal_weight * accuracy_weight
        weights.append(weight)
    
    # Normalize weights
    total_weight = sum(weights)
    if total_weight == 0:
        weights = [1] * len(observations)
        total_weight = len(observations)
    
    normalized_weights = [w / total_weight for w in weights]
    
    # Calculate weighted centroid
    weighted_lat = sum(obs.latitude * w for obs, w in zip(observations, normalized_weights))
    weighted_lon = sum(obs.longitude * w for obs, w in zip(observations, normalized_weights))
    
    # Calculate uncertainty as the weighted average distance from centroid
    # plus the average GPS accuracy
    distances = [
        haversine_distance(weighted_lat, weighted_lon, obs.latitude, obs.longitude)
        for obs in observations
    ]
    
    weighted_distance = sum(d * w for d, w in zip(distances, normalized_weights))
    avg_gps_accuracy = sum(obs.accuracy for obs in observations) / len(observations)
    
    # Uncertainty is combination of spread and GPS accuracy
    uncertainty = weighted_distance + avg_gps_accuracy
    
    return weighted_lat, weighted_lon, uncertainty


def parse_wigle_csv(filepath: Path, min_observations: int = 3) -> List[TriangulatedAP]:
    """
    Parse a Wigle CSV file and return triangulated access points
    
    Args:
        filepath: Path to the Wigle CSV file
        min_observations: Minimum number of observations required for triangulation
    
    Returns:
        List of triangulated access points
    """
    # Group observations by MAC address
    ap_observations = defaultdict(list)
    ap_ssids = {}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        # Skip the first metadata line (Wigle CSV has a metadata line before the actual CSV header)
        first_line = f.readline()
        
        # Now read as CSV with proper headers
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                mac = row.get('MAC', '').strip().upper()
                ssid = row.get('SSID', '').strip()
                
                # Skip if MAC is empty
                if not mac:
                    continue
                
                lat = float(row.get('CurrentLatitude', row.get('Lat', 0)))
                lon = float(row.get('CurrentLongitude', row.get('Lon', 0)))
                
                # Signal strength (RSSI)
                signal = int(row.get('RSSI', row.get('Signal', -100)))
                
                # GPS accuracy (default to 10m if not provided)
                accuracy = float(row.get('Accuracy', row.get('AccuracyMeters', 10)))
                
                # Skip invalid coordinates
                if lat == 0 and lon == 0:
                    continue
                
                observation = APObservation(
                    latitude=lat,
                    longitude=lon,
                    signal_strength=signal,
                    accuracy=accuracy
                )
                
                ap_observations[mac].append(observation)
                
                # Store SSID (keep the first non-empty one)
                if mac not in ap_ssids and ssid:
                    ap_ssids[mac] = ssid
                elif mac in ap_ssids and not ap_ssids[mac] and ssid:
                    ap_ssids[mac] = ssid
                    
            except (ValueError, KeyError) as e:
                # Skip malformed rows
                print(f"Warning: Skipping malformed row: {e}")
                continue
    
    # Triangulate positions for APs with enough observations
    triangulated_aps = []
    
    for mac, observations in ap_observations.items():
        if len(observations) >= min_observations:
            lat, lon, uncertainty = triangulate_position(observations)
            
            ap = TriangulatedAP(
                mac=mac,
                ssid=ap_ssids.get(mac, ''),
                latitude=lat,
                longitude=lon,
                uncertainty=uncertainty,
                observation_count=len(observations)
            )
            triangulated_aps.append(ap)
    
    return triangulated_aps


def create_kml(aps: List[TriangulatedAP], output_path: Path):
    """
    Create a KML file for Google Earth with placemark and accuracy circles
    
    Args:
        aps: List of triangulated access points
        output_path: Path to save the KML file
    """
    # Create KML root
    kml = ET.Element('kml', xmlns='http://www.opengis.net/kml/2.2')
    document = ET.SubElement(kml, 'Document')
    
    # Add document name and description
    name = ET.SubElement(document, 'name')
    name.text = 'Triangulated WiFi Access Points'
    
    description = ET.SubElement(document, 'description')
    description.text = f'Triangulated positions of {len(aps)} access points from Wigle wardriving data'
    
    # Define styles
    # Style for the center point
    point_style = ET.SubElement(document, 'Style', id='apPoint')
    icon_style = ET.SubElement(point_style, 'IconStyle')
    icon = ET.SubElement(icon_style, 'Icon')
    href = ET.SubElement(icon, 'href')
    href.text = 'http://maps.google.com/mapfiles/kml/shapes/wifi.png'
    
    # Style for the accuracy circle
    circle_style = ET.SubElement(document, 'Style', id='accuracyCircle')
    line_style = ET.SubElement(circle_style, 'LineStyle')
    line_color = ET.SubElement(line_style, 'color')
    line_color.text = '7f0000ff'  # Semi-transparent red
    line_width = ET.SubElement(line_style, 'width')
    line_width.text = '2'
    poly_style = ET.SubElement(circle_style, 'PolyStyle')
    poly_color = ET.SubElement(poly_style, 'color')
    poly_color.text = '3f0000ff'  # More transparent red fill
    
    # Add each AP as a folder - QGIS will create one layer per folder
    for ap in aps:
        # Use a naming scheme that groups point and circle together when sorted
        ap_label = ap.ssid or ap.mac
        
        # Create folder for this AP
        folder = ET.SubElement(document, 'Folder')
        folder_name = ET.SubElement(folder, 'name')
        folder_name.text = ap_label
        
        # Add center point
        placemark = ET.SubElement(folder, 'Placemark')
        pm_name = ET.SubElement(placemark, 'name')
        pm_name.text = 'Point'
        
        # Add ExtendedData for QGIS attribute table
        extended_data = ET.SubElement(placemark, 'ExtendedData')
        
        mac_data = ET.SubElement(extended_data, 'Data', name='MAC')
        mac_value = ET.SubElement(mac_data, 'value')
        mac_value.text = ap.mac
        
        ssid_data = ET.SubElement(extended_data, 'Data', name='SSID')
        ssid_value = ET.SubElement(ssid_data, 'value')
        ssid_value.text = ap.ssid or 'Hidden'
        
        obs_data = ET.SubElement(extended_data, 'Data', name='Observations')
        obs_value = ET.SubElement(obs_data, 'value')
        obs_value.text = str(ap.observation_count)
        
        unc_data = ET.SubElement(extended_data, 'Data', name='Uncertainty_m')
        unc_value = ET.SubElement(unc_data, 'value')
        unc_value.text = f'{ap.uncertainty:.1f}'
        
        pm_style = ET.SubElement(placemark, 'styleUrl')
        pm_style.text = '#apPoint'
        point = ET.SubElement(placemark, 'Point')
        coordinates = ET.SubElement(point, 'coordinates')
        coordinates.text = f'{ap.longitude},{ap.latitude},0'
        
        # Add accuracy circle
        circle_placemark = ET.SubElement(folder, 'Placemark')
        circle_name = ET.SubElement(circle_placemark, 'name')
        circle_name.text = 'Circle'
        
        # Add ExtendedData for QGIS attribute table
        circle_extended_data = ET.SubElement(circle_placemark, 'ExtendedData')
        
        circle_mac_data = ET.SubElement(circle_extended_data, 'Data', name='MAC')
        circle_mac_value = ET.SubElement(circle_mac_data, 'value')
        circle_mac_value.text = ap.mac
        
        circle_ssid_data = ET.SubElement(circle_extended_data, 'Data', name='SSID')
        circle_ssid_value = ET.SubElement(circle_ssid_data, 'value')
        circle_ssid_value.text = ap.ssid or 'Hidden'
        
        circle_obs_data = ET.SubElement(circle_extended_data, 'Data', name='Observations')
        circle_obs_value = ET.SubElement(circle_obs_data, 'value')
        circle_obs_value.text = str(ap.observation_count)
        
        circle_unc_data = ET.SubElement(circle_extended_data, 'Data', name='Uncertainty_m')
        circle_unc_value = ET.SubElement(circle_unc_data, 'value')
        circle_unc_value.text = f'{ap.uncertainty:.1f}'
        
        circle_style_url = ET.SubElement(circle_placemark, 'styleUrl')
        circle_style_url.text = '#accuracyCircle'
        
        polygon = ET.SubElement(circle_placemark, 'Polygon')
        extrude = ET.SubElement(polygon, 'extrude')
        extrude.text = '0'
        tesselate = ET.SubElement(polygon, 'tessellate')
        tesselate.text = '1'
        altitude_mode = ET.SubElement(polygon, 'altitudeMode')
        altitude_mode.text = 'clampToGround'
        outer_boundary = ET.SubElement(polygon, 'outerBoundaryIs')
        linear_ring = ET.SubElement(outer_boundary, 'LinearRing')
        circle_coords = ET.SubElement(linear_ring, 'coordinates')
        
        # Generate circle coordinates (approximate using polygon)
        circle_points = create_circle_coordinates(ap.latitude, ap.longitude, ap.uncertainty)
        circle_coords.text = ' '.join([f'{lon},{lat},0' for lat, lon in circle_points])
    
    # Pretty print and save
    xml_string = ET.tostring(kml, encoding='utf-8')
    dom = minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8')
    
    with open(output_path, 'wb') as f:
        f.write(pretty_xml)


def create_circle_coordinates(lat: float, lon: float, radius_meters: float, num_points: int = 64) -> List[Tuple[float, float]]:
    """
    Create coordinates for a circle around a point
    
    Args:
        lat: Center latitude
        lon: Center longitude
        radius_meters: Radius in meters
        num_points: Number of points to approximate the circle
    
    Returns:
        List of (latitude, longitude) tuples forming a circle
    """
    R = 6371000  # Earth's radius in meters
    
    points = []
    for i in range(num_points + 1):  # +1 to close the circle
        angle = 2 * math.pi * i / num_points
        
        # Calculate offset in radians
        d_lat = (radius_meters * math.cos(angle)) / R
        d_lon = (radius_meters * math.sin(angle)) / (R * math.cos(math.radians(lat)))
        
        point_lat = lat + math.degrees(d_lat)
        point_lon = lon + math.degrees(d_lon)
        
        points.append((point_lat, point_lon))
    
    return points


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Triangulate WiFi access point locations from Wigle wardriving CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Example:
  %(prog)s input.csv -o output.kml -m 3
  %(prog)s wigledata.csv --min-observations 5 --output triangulated.kml
        '''
    )
    
    parser.add_argument(
        'input',
        type=Path,
        help='Input Wigle CSV file'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=None,
        help='Output KML file (default: input filename with .kml extension)'
    )
    
    parser.add_argument(
        '-m', '--min-observations',
        type=int,
        default=3,
        help='Minimum number of observations required for triangulation (default: 3)'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    if not args.input.exists():
        print(f"Error: Input file '{args.input}' not found")
        return 1
    
    # Determine output filename
    if args.output is None:
        args.output = args.input.with_suffix('.kml')
    
    print(f"Reading Wigle CSV file: {args.input}")
    print(f"Minimum observations: {args.min_observations}")
    
    # Parse CSV and triangulate
    try:
        triangulated_aps = parse_wigle_csv(args.input, args.min_observations)
    except Exception as e:
        print(f"Error parsing CSV file: {e}")
        return 1
    
    if not triangulated_aps:
        print("No access points found with enough observations for triangulation")
        return 1
    
    print(f"Found {len(triangulated_aps)} access points with {args.min_observations}+ observations")
    
    # Calculate statistics
    avg_uncertainty = sum(ap.uncertainty for ap in triangulated_aps) / len(triangulated_aps)
    max_observations = max(ap.observation_count for ap in triangulated_aps)
    
    print(f"Average uncertainty: {avg_uncertainty:.1f}m")
    print(f"Maximum observations for a single AP: {max_observations}")
    
    # Create KML file
    print(f"Creating KML file: {args.output}")
    try:
        create_kml(triangulated_aps, args.output)
    except Exception as e:
        print(f"Error creating KML file: {e}")
        return 1
    
    print("Done! Import the KML file into Google Earth to visualize the results.")
    return 0


if __name__ == '__main__':
    exit(main())
