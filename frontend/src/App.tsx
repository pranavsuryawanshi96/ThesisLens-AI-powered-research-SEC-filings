import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AuthProvider } from "@/components/auth-provider"
import { ProtectedRoute } from "@/components/protected-route"
import { ChatLayout } from "@/pages/chat/chat-layout"
import { ChatsPage } from "@/pages/chat/chats-page"
import { ThreadPage } from "@/pages/chat/thread-page"
import { LoginPage } from "@/pages/login-page"
import { SignupPage } from "@/pages/signup-page"

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/chats" element={<ChatLayout />}>
              <Route index element={<ChatsPage />} />
              <Route path=":threadId" element={<ThreadPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/chats" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
