"""Regression checks for bead plates beside coloured count legends."""
import unittest
import cv2
import numpy as np

from road_vision import parse_baccarat_road_image, _six_row_regions


SEQUENCE = list('閒和閒莊莊閒' + '閒閒閒閒閒閒' + '和莊閒和莊莊' + '莊閒閒莊')
COLOURS = {'莊': (0, 0, 230), '閒': (230, 100, 0), '和': (0, 160, 0)}


def board(legend=True, overlay=False):
    image = np.full((440, 600, 3), 255, np.uint8)
    for i, label in enumerate(SEQUENCE):
        cx, cy = 60 + (i//6)*43, 50 + (i%6)*43
        cv2.circle(image, (cx, cy), 20, COLOURS[label], -1)
        # White central marks simulate glyphs without font dependencies.
        cv2.rectangle(image, (cx-4, cy-10), (cx+4, cy+10), (255,255,255), -1)
        if overlay and i == 15:
            cv2.circle(image, (cx+11, cy+11), 7, COLOURS['閒'], -1)
    if legend:
        for x, label in zip((60,146,232), ('莊','閒','和')):
            cv2.rectangle(image, (x-20, 308), (x+20, 348), COLOURS[label], -1)
    return image


def parse(image, minimum=15):
    return parse_baccarat_road_image(cv2.imencode('.png', image)[1].tobytes(), minimum)


class BeadPlateRegressionTests(unittest.TestCase):
    def test_plain_and_adjacent_legend_have_identical_order(self):
        for legend in (False, True):
            for overlay in (False, True):
                with self.subTest(legend=legend, overlay=overlay):
                    result = parse(board(legend, overlay))
                    self.assertTrue(result.accepted, result.note)
                    self.assertEqual(result.sequence, SEQUENCE)
                    self.assertEqual((result.rows, result.cols), (6,4))

    def test_hole_in_middle_is_rejected(self):
        image = board()
        image[73:115,82:125] = 255
        self.assertFalse(parse(image).accepted)

    def test_unreadable_cell_is_not_guessed(self):
        image = board()
        cv2.circle(image, (146,179), 20, (150,150,150), -1)
        self.assertFalse(parse(image).accepted)

    def test_multiple_boards_are_ambiguous(self):
        image = np.hstack((board(False),board(False)))
        result = parse(image)
        self.assertFalse(result.accepted)
        self.assertEqual(result.mode, 'ambiguous')

    def test_minimum_main_results_still_enforced(self):
        self.assertFalse(parse(board(),20).accepted)

    def test_seven_regular_rows_cannot_be_sliced(self):
        points=[{'x':x, 'y':y} for x in (40,80,120) for y in range(40,281,40)]
        self.assertEqual(list(_six_row_regions(points,40)), [])

    def test_big_road_only_is_not_accepted(self):
        image=np.full((400,600,3),255,np.uint8)
        for ci, length in enumerate((3,4,2,5,4)):
            for ri in range(length):
                cv2.circle(image,(40+ci*43,40+ri*43),18,COLOURS['莊' if ci%2==0 else '閒'],3)
        self.assertFalse(parse(image).accepted)

    def test_invalid_image_is_rejected(self):
        self.assertFalse(parse_baccarat_road_image(b'invalid').accepted)


if __name__ == '__main__':
    unittest.main()
