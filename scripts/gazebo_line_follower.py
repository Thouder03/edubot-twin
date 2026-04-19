#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rospy
import cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image

class GazeboLineFollower:
    def __init__(self):
        rospy.init_node('gazebo_line_follower')

        # 图像订阅：根据您的实际摄像头话题修改，通常是 /camera/image_raw
        self.image_topic = "/image_raw"  # 您系统中实际存在的摄像头图像话题
        self.image_sub = rospy.Subscriber(self.image_topic, Image, self.image_callback)

        # 速度控制
        self.cmd_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)

        # OpenCV桥接
        self.bridge = CvBridge()

        # 控制参数
        self.kp = 0.003  # 比例增益，根据实际效果调整 [0.001 ~ 0.01]
        self.desired_center = 320  # 图像宽度为640，中心为320

        # 显示调试窗口（可选）
        cv2.namedWindow("ROI View", 1)
        cv2.namedWindow("Mask View", 1)

        self.rate = rospy.Rate(20)  # 20Hz

    def image_callback(self, data):
        try:
            # 将ROS图像转为OpenCV格式（格式为 RGB8，对应 OpenCV BGR）
            cv_image = self.bridge.imgmsg_to_cv2(data, "bgr8")
        except CvBridgeError as e:
            rospy.logerr("CvBridge Error: %s" % e)
            return

        height, width, _ = cv_image.shape

        # 只处理图像下半部分，排除背景干扰，提高巡线稳定性
        roi = cv_image[int(height * 0.5):height, 0:width]  # 下半部分

        # 转为 HSV 颜色空间，便于提取 黑色 或 其它颜色线条
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # ======================
        # 针对黑色线的优化设置
        # 根据您提供的HSV值(0,0,26)进行调整
        # ======================
        
        # 黑色线的HSV范围 - 基于您提供的值(0,0,26)进行扩展
        # 黑色特点：V值很低，H和S值范围较宽
        lower_black = np.array([0, 0, 0])           # H:0-180, S:0-50, V:0-30
        upper_black = np.array([180, 50, 30])      # 根据您的值(0,0,26)设置上限
        
        # 创建黑色掩码
        mask = cv2.inRange(hsv, lower_black, upper_black)

        # 形态学操作去除噪声
        kernel = np.ones((3,3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        # 可选：降噪
        mask = cv2.medianBlur(mask, 5)

        # 计算线的位置
        M = cv2.moments(mask)

        twist = Twist()

        if M["m00"] > 100:  # 检测到线
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            cv2.circle(roi, (cx, cy), 5, (0, 255, 0), -1)
            cv2.line(roi, (cx, 0), (cx, roi.shape[0]), (0, 255, 0), 2)

            error_x = cx - self.desired_center

            # === 1. 降低 P 增益，减少震荡 ===
            kp = 0.0015  # 从 0.003 降低到 0.0015（根据实际情况可再调）

            # === 2. 基础角速度计算 ===
            raw_angular_z = -float(error_x) * kp

            # === 3. 角速度平滑滤波（指数移动平均）===
            if not hasattr(self, 'filtered_angular_z'):
                self.filtered_angular_z = 0.0
            alpha = 0.7  # 平滑系数：越大响应越快，越小越平滑（建议 0.6~0.8）
            self.filtered_angular_z = alpha * raw_angular_z + (1 - alpha) * self.filtered_angular_z

            # === 4. 限制角速度范围 ===
            angular_z = max(-0.4, min(0.4, self.filtered_angular_z))  # 适当降低最大角速度

            # === 5. 动态线速度（更平缓的减速）===
            max_linear_speed = 0.2
            min_linear_speed = 0.1

            # 使用平方根函数使减速更平缓（避免急弯突然变很慢）
            normalized_error = abs(error_x) / float(self.desired_center)
            speed_factor = max(0.0, 1.0 - np.sqrt(normalized_error))  # sqrt 比线性更平滑

            twist.linear.x = max(min_linear_speed, max_linear_speed * speed_factor)
            twist.angular.z = angular_z

            rospy.loginfo_throttle(0.5,
                f"位置: {cx}, 误差: {error_x:.1f}, "
                f"线速度: {twist.linear.x:.3f}, 角速度: {angular_z:.3f}")
        else:
            # 未检测到线，停止
            twist.linear.x = 0.0
            twist.angular.z = 0.0
            # 重置滤波状态
            if hasattr(self, 'filtered_angular_z'):
                del self.filtered_angular_z
            rospy.logwarn_throttle(1, "未检测到黑线！")

        self.cmd_pub.publish(twist)

        # 显示图像（调试用，可选）
        cv2.imshow("ROI View", roi)
        cv2.imshow("Mask View", mask)
        cv2.waitKey(1)

        self.rate.sleep()

    def run(self):
        rospy.spin()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    try:
        node = GazeboLineFollower()
        node.run()
    except rospy.ROSInterruptException:
        pass