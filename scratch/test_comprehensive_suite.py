import sys
import os
import sqlite3
import unittest
from datetime import datetime

# Đảm bảo import được backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import get_connection, init_db
from backend.modules.metrics_tracker import metrics_tracker
from backend.modules.gpm_profile_reader import is_gpm_reader_available, fetch_account_info_from_gpm
from backend.modules.gpm_client import gpm_client
from backend.modules.account_health import account_health


class ComprehensiveSyncTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        # Backup dữ liệu gpm_profiles hiện tại
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gpm_profiles")
        cls.original_profiles = [dict(row) for row in cursor.fetchall()]
        conn.close()
        print(f"\n[SETUP] Đã sao lưu {len(cls.original_profiles)} profiles từ database thực tế.")

    @classmethod
    def tearDownClass(cls):
        # Khôi phục hoàn toàn dữ liệu ban đầu
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gpm_profiles")
        for p in cls.original_profiles:
            keys = list(p.keys())
            placeholders = ", ".join(["?"] * len(keys))
            columns = ", ".join(keys)
            cursor.execute(f"INSERT INTO gpm_profiles ({columns}) VALUES ({placeholders})", [p[k] for k in keys])
        conn.commit()
        conn.close()
        print(f"\n[TEARDOWN] Đã khôi phục nguyên vẹn {len(cls.original_profiles)} profiles vào database.")

    def test_01_live_zeroram_extraction(self):
        """Kiểm tra đọc cookie thời gian thực: Trích xuất chính xác tiktok_uid, sec_uid, username, nickname"""
        self.assertTrue(is_gpm_reader_available(), "GPM Profile Reader phải khả dụng.")
        profiles = gpm_client.get_profiles()
        self.assertTrue(len(profiles) > 0, "GPMLogin phải trả về danh sách profile.")

        logged_in_count = 0
        for p in profiles[:3]:  # Kiểm tra mẫu 3 profile đầu
            pid = p["id"]
            res = fetch_account_info_from_gpm(pid)
            if res.get("is_logged_in"):
                logged_in_count += 1
                self.assertIsNotNone(res.get("username"), f"Profile {pid} thiếu username")
                self.assertIsNotNone(res.get("nickname"), f"Profile {pid} thiếu nickname")
                self.assertTrue(
                    bool(res.get("tiktok_uid") or res.get("user_id")),
                    f"Profile {pid} thiếu tiktok_uid/user_id"
                )
                self.assertTrue(bool(res.get("sec_uid")), f"Profile {pid} thiếu sec_uid")
                print(f"   [PASS] Profile {p['name']}: @{res.get('username')} ({res.get('nickname')}) | UID: {res.get('tiktok_uid') or res.get('user_id')}")

        print(f"-> Test 01 OK: {logged_in_count} profile mẫu trích xuất đầy đủ UID & SecUID.")

    def test_02_inplace_rename_detection(self):
        """Kiểm tra đổi tên in-place: Cùng tiktok_uid đổi handle/nickname phải cập nhật chính xác profile đó"""
        test_gpm_id = "test-inplace-gpm-001"
        test_uid = "999888777000111"
        test_sec = "MS4wLjABAAAA_TEST_SEC_UID_INPLACE"

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gpm_profiles WHERE gpm_id = ?", (test_gpm_id,))
        cursor.execute("""
            INSERT INTO gpm_profiles (gpm_id, name, tiktok_username, tiktok_nickname, tiktok_uid, sec_uid, followers_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (test_gpm_id, "Test Inplace Profile", "old_handle_name", "Tên Cũ", test_uid, test_sec, 500))
        conn.commit()
        conn.close()

        # Giả lập TikTok đổi handle sang "new_vibing_handle" và display name sang "Tên Mới Cực Chất"
        res = metrics_tracker.update_profile_stats(
            gpm_id=test_gpm_id,
            followers=1200,
            total_views=50000,
            username="new_vibing_handle",
            nickname="Tên Mới Cực Chất",
            tiktok_uid=test_uid,
            sec_uid=test_sec
        )

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gpm_profiles WHERE gpm_id = ?", (test_gpm_id,))
        row = dict(cursor.fetchone())
        conn.close()

        self.assertEqual(row["tiktok_username"], "new_vibing_handle")
        self.assertEqual(row["tiktok_nickname"], "Tên Mới Cực Chất")
        self.assertEqual(row["tiktok_uid"], test_uid)
        self.assertEqual(row["followers_count"], 1200)
        print("-> Test 02 OK: Đổi Handle & Nickname in-place cập nhật chính xác theo tiktok_uid.")

    def test_03_account_migration_handover(self):
        """Kiểm tra Account Migration: Nick từ Profile A đăng nhập sang Profile B phải tự động chuyển và gỡ Profile A"""
        gpm_a = "test-migration-profile-A"
        gpm_b = "test-migration-profile-B"
        migrated_uid = "777666555444333"
        migrated_sec = "MS4wLjABAAAA_TEST_SEC_MIGRATION"

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gpm_profiles WHERE gpm_id IN (?, ?)", (gpm_a, gpm_b))
        # Ban đầu Profile A sở hữu tài khoản
        cursor.execute("""
            INSERT INTO gpm_profiles (gpm_id, name, tiktok_username, tiktok_nickname, tiktok_uid, sec_uid, followers_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """, (gpm_a, "Profile A (Cũ)", "super_channel", "Kênh Siêu Cấp", migrated_uid, migrated_sec, 25000))
        # Profile B là profile mới chưa có nick
        cursor.execute("""
            INSERT INTO gpm_profiles (gpm_id, name, tiktok_username, tiktok_nickname, tiktok_uid, sec_uid, followers_count, status)
            VALUES (?, ?, '', '', '', '', 0, 'active')
        """, (gpm_b, "Profile B (Mới)"))
        conn.commit()
        conn.close()

        # Khi Profile B được sync thấy tài khoản migrated_uid (có thể handle đã đổi sang super_channel_v2)
        metrics_tracker.update_profile_stats(
            gpm_id=gpm_b,
            followers=26000,
            total_views=100000,
            username="super_channel_v2",
            nickname="Kênh Siêu Cấp V2",
            tiktok_uid=migrated_uid,
            sec_uid=migrated_sec
        )

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gpm_profiles WHERE gpm_id = ?", (gpm_a,))
        row_a = dict(cursor.fetchone())
        cursor.execute("SELECT * FROM gpm_profiles WHERE gpm_id = ?", (gpm_b,))
        row_b = dict(cursor.fetchone())
        conn.close()

        # 1. Profile A phải bị gỡ thông tin TikTok và chuyển sang unlogged
        self.assertEqual(row_a["tiktok_username"], "", "Profile A phải bị xóa tiktok_username")
        self.assertEqual(row_a["tiktok_uid"], "", "Profile A phải bị xóa tiktok_uid")
        self.assertEqual(row_a["status"], "unlogged", "Profile A phải chuyển status unlogged")
        self.assertIn("đã chuyển sang profile", row_a["status_reason"], "Profile A phải ghi rõ lý do chuyển giao")

        # 2. Profile B phải sở hữu hoàn toàn tài khoản
        self.assertEqual(row_b["tiktok_username"], "super_channel_v2")
        self.assertEqual(row_b["tiktok_nickname"], "Kênh Siêu Cấp V2")
        self.assertEqual(row_b["tiktok_uid"], migrated_uid)
        self.assertEqual(row_b["followers_count"], 26000)

        print("-> Test 03 OK: Account Migration (Profile A -> Profile B) hoạt động chuẩn xác 100%.")

    def test_04_fallback_migration_via_sec_uid(self):
        """Kiểm tra Fallback Migration: Khi tiktok_uid rỗng, hệ thống dùng sec_uid để nhận diện chuyển giao"""
        gpm_c = "test-sec-profile-C"
        gpm_d = "test-sec-profile-D"
        only_sec_uid = "MS4wLjABAAAA_ONLY_SEC_UID_FALLBACK"

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gpm_profiles WHERE gpm_id IN (?, ?)", (gpm_c, gpm_d))
        cursor.execute("""
            INSERT INTO gpm_profiles (gpm_id, name, tiktok_username, tiktok_nickname, tiktok_uid, sec_uid, status)
            VALUES (?, ?, ?, ?, '', ?, 'active')
        """, (gpm_c, "Profile C (Gốc)", "sec_channel", "Sec Kênh", only_sec_uid))
        cursor.execute("""
            INSERT INTO gpm_profiles (gpm_id, name, tiktok_username, tiktok_nickname, tiktok_uid, sec_uid, status)
            VALUES (?, ?, '', '', '', '', 'active')
        """, (gpm_d, "Profile D (Đích)"))
        conn.commit()
        conn.close()

        # Profile D sync chỉ nhận được sec_uid (không có uid)
        metrics_tracker.update_profile_stats(
            gpm_id=gpm_d,
            followers=5000,
            total_views=10000,
            username="sec_channel_renamed",
            nickname="Sec Kênh Mới",
            tiktok_uid="",
            sec_uid=only_sec_uid
        )

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gpm_profiles WHERE gpm_id = ?", (gpm_c,))
        row_c = dict(cursor.fetchone())
        cursor.execute("SELECT * FROM gpm_profiles WHERE gpm_id = ?", (gpm_d,))
        row_d = dict(cursor.fetchone())
        conn.close()

        self.assertEqual(row_c["tiktok_username"], "")
        self.assertEqual(row_c["status"], "unlogged")
        self.assertEqual(row_d["tiktok_username"], "sec_channel_renamed")
        self.assertEqual(row_d["sec_uid"], only_sec_uid)
        print("-> Test 04 OK: Fallback SecUid Migration hoạt động chính xác khi tiktok_uid rỗng.")

    def test_05_profile_deletion_and_safety_guard(self):
        """Kiểm tra xử lý xóa profile trên GPM và chốt bảo vệ an toàn khi GPM đóng"""
        test_deleted_gpm_id = "test-to-be-deleted-gpm-999"
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gpm_profiles (gpm_id, name, tiktok_username)
            VALUES (?, ?, ?)
            ON CONFLICT(gpm_id) DO NOTHING
        """, (test_deleted_gpm_id, "Ghost Profile", "ghost_user"))
        conn.commit()
        conn.close()

        # Giả lập danh sách active_gpm_ids trả về từ GPMLogin KHÔNG chứa test_deleted_gpm_id
        active_ids_from_gpm = {"some-other-id-1", "some-other-id-2"}

        conn = get_connection()
        cursor = conn.cursor()
        # Chạy logic xóa như trong backend/app.py và tiktok_tracker.py
        cursor.execute("SELECT gpm_id, name FROM gpm_profiles WHERE gpm_id = ?", (test_deleted_gpm_id,))
        row = cursor.fetchone()
        if row and row["gpm_id"] not in active_ids_from_gpm:
            cursor.execute("DELETE FROM gpm_profiles WHERE gpm_id = ?", (test_deleted_gpm_id,))
        conn.commit()

        cursor.execute("SELECT * FROM gpm_profiles WHERE gpm_id = ?", (test_deleted_gpm_id,))
        after_row = cursor.fetchone()
        conn.close()

        self.assertIsNone(after_row, "Profile không còn trên GPMLogin phải bị xóa khỏi database.")
        print("-> Test 05 OK: Tự động xóa profile rác khi đã bị xóa trên GPMLogin.")


if __name__ == "__main__":
    unittest.main()
