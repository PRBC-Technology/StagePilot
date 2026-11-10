import unittest

from stagepilot.controller import Detection, Motion, recommend


class ControllerTests(unittest.TestCase):
    def test_centered_is_stationary(self):
        self.assertEqual(recommend(Detection(.5, .45, .45, .9)), Motion())

    def test_direction_and_speed_limits(self):
        result = recommend(Detection(1, 0, .1, 1))
        self.assertEqual((result.pan, result.tilt, result.zoom), (.3, .3, .15))

    def test_loss_low_confidence_and_invalid_stop(self):
        for detection in (None, Detection(.8, .4, .4, .2),
                          Detection(float('nan'), .4, .4, .9),
                          Detection(.5, .5, 0, .9)):
            result = recommend(detection)
            self.assertEqual((result.pan, result.tilt, result.zoom), (0, 0, 0))
            self.assertNotEqual(result.reason, 'tracking')


if __name__ == '__main__':
    unittest.main()
