<!--
  学生自助注册页
-->
<template>
  <div class="register-container">
    <div class="register-box">
      <div class="register-header">
        <h1 class="register-title">学生注册</h1>
        <p class="register-subtitle">Campus Innovation &amp; Entrepreneurship</p>
      </div>

      <el-form
        ref="registerFormRef"
        :model="registerForm"
        :rules="registerRules"
        class="register-form"
        label-width="80px"
      >
        <el-form-item label="学号" prop="username">
          <el-input v-model="registerForm.username" placeholder="请输入学号" maxlength="64" />
        </el-form-item>

        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="registerForm.real_name" placeholder="请输入真实姓名" maxlength="64" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="registerForm.password"
            type="password"
            show-password
            placeholder="6位纯数字"
            maxlength="6"
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="registerForm.confirmPassword"
            type="password"
            show-password
            placeholder="请再次输入密码"
            maxlength="6"
          />
        </el-form-item>

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="registerForm.email" placeholder="请输入邮箱" maxlength="128" />
        </el-form-item>

        <el-form-item label="手机号" prop="phone">
          <el-input v-model="registerForm.phone" placeholder="选填，11位手机号" maxlength="11" />
        </el-form-item>

        <el-form-item label="所属学院" prop="college_id">
          <el-select v-model="registerForm.college_id" placeholder="请选择学院" filterable style="width: 100%">
            <el-option
              v-for="c in collegeOptions"
              :key="c.id"
              :label="c.college_name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            class="register-btn"
            :loading="loading"
            @click="handleRegister"
          >
            注 册
          </el-button>
        </el-form-item>

        <el-form-item>
          <el-button link type="primary" @click="$router.push('/login')">已有账号？返回登录</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { register, getColleges } from '@/api/auth'
import { passwordValidator } from '@/utils/validators'

const router = useRouter()
const registerFormRef = ref<FormInstance>()
const loading = ref(false)
const collegeOptions = ref<any[]>([])

const registerForm = reactive({
  username: '',
  real_name: '',
  password: '',
  confirmPassword: '',
  email: '',
  phone: '',
  college_id: undefined as number | undefined,
})

const validateConfirmPassword = (_rule: any, value: string, callback: any) => {
  if (value !== registerForm.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const registerRules: FormRules = {
  username: [{ required: true, message: '请输入学号', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [
    { required: true, validator: passwordValidator(true, '密码'), trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
  email: [
    { required: true, type: 'email', message: '请输入正确的邮箱', trigger: 'blur' },
  ],
  college_id: [{ required: true, message: '请选择学院', trigger: 'change' }],
}

async function handleRegister() {
  if (!registerFormRef.value) return
  await registerFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await register({
        username: registerForm.username,
        password: registerForm.password,
        real_name: registerForm.real_name,
        email: registerForm.email,
        phone: registerForm.phone || undefined,
        college_id: registerForm.college_id,
      })
      ElMessage.success('注册成功，请登录')
      router.push('/login')
    } finally {
      loading.value = false
    }
  })
}

onMounted(async () => {
  try {
    const res = await getColleges()
    collegeOptions.value = (res as any).data || []
  } catch {
    // ignore
  }
})
</script>

<style scoped>
.register-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f5f7fa;
}

:deep(html.dark) .register-container {
  background-color: #141414;
}

.register-box {
  width: 460px;
  padding: 36px 40px;
  background: #ffffff;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.06);
}

:deep(html.dark) .register-box {
  background: #1f1f1f;
  border-color: #2b2b2b;
}

.register-header {
  text-align: center;
  margin-bottom: 24px;
}

.register-title {
  font-size: 22px;
  color: #303133;
  margin-bottom: 6px;
  font-weight: 600;
}

:deep(html.dark) .register-title {
  color: #e5eaf3;
}

.register-subtitle {
  font-size: 12px;
  color: #909399;
  letter-spacing: 0.5px;
}

.register-form {
  margin-top: 16px;
}

.register-btn {
  width: 100%;
}
</style>
