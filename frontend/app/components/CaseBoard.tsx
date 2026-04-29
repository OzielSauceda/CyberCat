export default function CaseBoard({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative bg-foldermark min-h-screen">
      {children}
    </div>
  )
}
