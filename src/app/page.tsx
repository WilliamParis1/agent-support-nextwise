export default function Home() {
  return (
    <main style={{ 
      display: 'flex', 
      minHeight: '100vh', 
      flexDirection: 'column', 
      alignItems: 'center', 
      justifyContent: 'center', 
      padding: '96px' 
    }}>
      <div style={{ textAlign: 'center' }}>
        <h1 style={{ fontSize: '2.25rem', fontWeight: 'bold', marginBottom: '1rem' }}>
          Welcome to Nextwise
        </h1>
        <p style={{ fontSize: '1.25rem', color: '#6b7280' }}>
          Agent Support Application
        </p>
      </div>
    </main>
  );
}
