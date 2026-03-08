from typing import List, Optional
from pydantic import BaseModel, Field

class UserProfile(BaseModel):
    """
    Bảng Hồ Sơ Tiềm Thức (Universal Core Persona).
    Lưu trữ toàn bộ SỰ THẬT (Facts) về User ở mọi ngành nghề, độ tuổi.
    """
    # 1. Định danh cốt lõi (Core Identity)
    name: Optional[str] = Field(default=None, description="Tên, biệt danh, hoặc cách xưng hô (VD: anh, chú, mình)")
    demographics: Optional[str] = Field(default=None, description="Nhân khẩu học: Tuổi, giới tính, quốc gia, nơi sinh sống")
    
    # 2. Vai trò xã hội (Social Role)
    occupation: Optional[str] = Field(default=None, description="Nghề nghiệp, chuyên môn, hoặc tình trạng (VD: Sinh viên Y, Đầu bếp, Đang thất nghiệp)")
    
    # 3. Mối quan hệ (Relationships)
    relationships: List[str] = Field(
        default_factory=list, 
        description="Gia đình, bạn bè, thú cưng, tình trạng hôn nhân (VD: Đã kết hôn, Có một chú chó tên Rex)"
    )

    # 4. Sở thích & Đam mê (Interests & Passions)
    interests: List[str] = Field(
        default_factory=list, 
        description="Sở thích, đam mê, game, phim ảnh, thể thao, món ăn yêu thích"
    )

    # 5. Kế hoạch & Mục tiêu (Goals & Activities)
    goals_and_plans: List[str] = Field(
        default_factory=list, 
        description="Mục tiêu ngắn/dài hạn, dự án cá nhân, hoặc kế hoạch (VD: Sắp đi du lịch Nhật Bản, Đang học chơi Piano, Đang viết sách)"
    )

    # 6. Thói quen & Ràng buộc (Preferences & Constraints) - CỰC KỲ QUAN TRỌNG
    preferences: List[str] = Field(
        default_factory=list, 
        description="Thói quen sinh hoạt, phong cách giao tiếp ưa thích (VD: Thích bot trả lời ngắn gọn, hay thức khuya)"
    )
    constraints: List[str] = Field(
        default_factory=list, 
        description="Ràng buộc cá nhân, dị ứng, bệnh lý, hoặc những điều cấm kỵ/ghét (VD: Dị ứng hải sản, Không thích nói chuyện chính trị)"
    )

    # 7. Kho lưu trữ mở rộng (Misc Facts)
    other_facts: List[str] = Field(
        default_factory=list, 
        description="Các sự thật quan trọng khác không lọt vào các danh mục trên"
    )