from datetime import datetime,timezone
from research_os.research.calibration import CalibrationLab
from research_os.intelligence.probability import CalibrationSample

def test_calibration_perfect():
    report=CalibrationLab().evaluate([CalibrationSample(.2,0),CalibrationSample(.8,1),CalibrationSample(.7,1),CalibrationSample(.3,0)])
    assert report.samples==4
    assert report.brier==0.065
    assert report.expected_calibration_error>0

def test_empty_calibration():
    report=CalibrationLab().evaluate([])
    assert report.samples==0
    assert report.buckets==()

def test_bucket_boundaries():
    report=CalibrationLab(bucket_count=5).evaluate([CalibrationSample(0.0,0),CalibrationSample(.999,1)])
    assert report.buckets[0].samples==1
    assert report.buckets[4].samples==1
